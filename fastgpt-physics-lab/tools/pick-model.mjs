#!/usr/bin/env node
/**
 * pick-model.mjs — 实测评比候选模型，为物理诊断工作流选出主模型
 *
 * 为什么需要它：模型列表里有 101 个模型，但"哪个适合考研物理错因分析"
 * 不能用猜的。本脚本用同一个真实物理诊断提示词逐个调用，记录：
 *   - 是否可用（连通性）
 *   - 延迟
 *   - 是否严格遵守 JSON 输出格式（工作流要用结构化输出）
 *   - 是否遵守"不得断言具体误区"这条关键约束
 *
 * 密钥从 env/.env 读取，不打印。
 *
 * 用法：node tools/pick-model.mjs [模型ID ...]
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const txt = fs.readFileSync(path.join(ROOT, 'env', '.env'), 'utf8');
const pick = (k) => {
  const m = txt.match(new RegExp('^' + k + '=(.*)$', 'm'));
  return m ? m[1].trim() : '';
};
const BASE = pick('GENAI_BASE_URL').replace(/\/+$/, '');
const KEY = pick('GENAI_API_KEY');

// 默认候选改成本账户**实测可用**的模型（旧默认含 DeepSeek-V3.2，实测被渠道限制 503）
const DEFAULTS = ['DeepSeek-V4-Flash', 'Kimi-K2.6', 'GLM-5.3', 'Qwen3.6-Flash'];
const models = process.argv.slice(2).length ? process.argv.slice(2) : DEFAULTS;

// 与 fastgpt/WORKFLOW.md §5 的错因分析提示词同构：考察 JSON 格式与"不断言"约束
const SYSTEM = `你是一位考研物理辅导老师，负责分析学生做错一道选择题的原因。

严格要求：
1. 只根据给出的信息判断，**绝不**断言学生存在某个具体误区。
   单选题的单个错选项无法区分"概念错误/公式误用/前置知识缺失/计算失误"。
2. 只输出 JSON，不要任何解释、不要 markdown 代码块标记。
3. JSON 结构必须是：
{"topic":"知识点","correct":false,"possible_misconceptions":["可能的误区1","可能的误区2"],"confidence":0.0-1.0,"recommended_review":["复习建议1"],"follow_up_question":"为区分上述可能原因，向学生提一个追问"}
4. possible_misconceptions 里每一项都必须体现"可能"，不得写成确定结论。`;

const USER = `题目：一质量为 m 的均匀圆柱体，在水平面上作纯滚动，质心速度为 v。此时它的总动能为？
A. (1/2)mv²
B. (3/4)mv²
C. mv²
D. (1/4)mv²

学生的作答：A
标准答案：B
标准解析：纯滚动时总动能 = 平动动能 + 绕质心转动动能 = (1/2)mv² + (1/2)Iω²。
圆柱 I = (1/2)mR²，纯滚动 v = ωR，故转动动能为 (1/4)mv²，总动能为 (3/4)mv²。
学生选 A 说明只算了平动动能，漏掉了转动部分。

请按系统提示的 JSON 结构输出诊断。`;

async function call(model) {
  const started = Date.now();
  try {
    const c = new AbortController();
    const t = setTimeout(() => c.abort(), 90000);
    const r = await fetch(`${BASE}/chat/completions`, {
      method: 'POST',
      signal: c.signal,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${KEY}` },
      body: JSON.stringify({
        model,
        messages: [
          { role: 'system', content: SYSTEM },
          { role: 'user', content: USER }
        ],
        temperature: 0.2,
        /*
         * max_tokens 必须给足，不能设小。
         *
         * 实测踩坑：这里原来是 700，结果多个模型返回空文本或半截 JSON，
         * 我据此误判"GLM 系列无法输出合法 JSON"。真实原因是：
         * 这些模型（GLM-5.3-Flash、DeepSeek-V4-Flash 等）会先输出
         * `reasoning_content`（思维链），而**思维链同样计入 completion tokens**。
         * 思维链吃掉 700 的配额后，正式答案就没有 token 可用了。
         * 调到 3000 后，三个模型都稳定给出完整 JSON。
         * 同一个坑对工作流也成立：工作流里 LLM 节点的 max_tokens 也必须给足。
         */
        max_tokens: 3000
      })
    });
    clearTimeout(t);
    const raw = await r.text();
    const ms = Date.now() - started;
    if (r.status !== 200) {
      // 错误信息里可能回显 key，做一次清洗
      return { model, ok: false, ms, note: `HTTP ${r.status}: ${raw.slice(0, 160).split(KEY).join('<KEY>')}` };
    }
    let j;
    try { j = JSON.parse(raw); } catch { return { model, ok: false, ms, note: '响应非 JSON' }; }
    const content = j.choices?.[0]?.message?.content ?? '';
    const finish = j.choices?.[0]?.finish_reason;
    const reasoning = j.choices?.[0]?.message?.reasoning_content ?? j.choices?.[0]?.message?.reasoning ?? '';
    const usage = j.usage || {};
    // 校验：能否解析出 JSON
    // 注意：不能只 trim 代码围栏。实测 GLM-5.3-Flash 会输出「```json {…} ```」，
    // 而个别模型会在 JSON 前后各带一句解释。因此统一取第一个 { 到最后一个 }。
    let parsed = null;
    let cleaned = String(content).replace(/^\s*```(?:json)?\s*/i, '').replace(/\s*```\s*$/, '').trim();
    const b = cleaned.indexOf('{');
    const e = cleaned.lastIndexOf('}');
    if (b >= 0 && e > b) cleaned = cleaned.slice(b, e + 1);
    try { parsed = JSON.parse(cleaned); } catch { /* 保持 null */ }
    const hasKeys = parsed && ['topic', 'correct', 'possible_misconceptions', 'confidence', 'recommended_review']
      .every((k) => k in parsed);
    const misconceptions = Array.isArray(parsed?.possible_misconceptions) ? parsed.possible_misconceptions : [];
    // "不得断言"约束：每条都应含可能性措辞
    const hedged = misconceptions.filter((s) => /可能|也许|或许|疑似|不排除|无法确定|难以判断/.test(String(s)));
    return {
      model,
      ok: true,
      ms,
      total: usage.total_tokens,
      completion: usage.completion_tokens,
      finish,
      reasoningChars: String(reasoning).length,
      jsonOk: Boolean(parsed),
      keysOk: hasKeys,
      nMis: misconceptions.length,
      nHedged: hedged.length,
      followUp: Boolean(parsed?.follow_up_question),
      topic: parsed?.topic,
      sample: misconceptions.slice(0, 2).map((s) => String(s).slice(0, 44))
    };
  } catch (e) {
    return { model, ok: false, ms: Date.now() - started, note: e.message };
  }
}

console.log('='.repeat(78));
console.log(' 候选模型实测评比（提示词与工作流错因分析节点同构）');
console.log(' 端点: ' + BASE);
console.log('='.repeat(78));

const results = [];
for (const m of models) {
  process.stdout.write(`  ${m.padEnd(24)} 调用中...`);
  const r = await call(m);
  results.push(r);
  process.stdout.write('\r');
  if (!r.ok) {
    console.log(`  ${m.padEnd(24)} ✗ ${r.note}`);
  } else {
    const flags = [
      r.jsonOk ? 'JSON✓' : 'JSON✗',
      r.keysOk ? '字段✓' : '字段✗',
      r.followUp ? '追问✓' : '追问✗',
      r.nMis ? `误区${r.nHedged}/${r.nMis}带可能措辞` : '无误区'
    ].join('  ');
    // 打印 finish_reason 与 completion tokens：
    // finish=length 说明被 max_tokens 截断，此时的 JSON✗ 是"配额不足"而非"模型不行"
    const diag = `finish=${r.finish} 输出=${r.completion ?? '?'}tok` +
      (r.reasoningChars ? ` 思维链=${r.reasoningChars}字符` : '') +
      (r.finish === 'length' ? '  ⚠ 被截断（需加大 max_tokens）' : '');
    console.log(`  ${m.padEnd(24)} ✓ ${String(r.ms).padStart(6)}ms  ${flags}`);
    console.log(`      ${diag}`);
    if (r.topic) console.log(`      topic=${r.topic}`);
    for (const s of r.sample || []) console.log(`      · ${s}`);
  }
}

console.log('\n' + '='.repeat(78));
console.log(' 评分（可用性 + 格式合规 + 遵守"不断言"约束 + 延迟）');
console.log('='.repeat(78));
const scored = results.map((r) => {
  if (!r.ok) return { ...r, score: -1 };
  let s = 0;
  if (r.jsonOk) s += 3;
  if (r.keysOk) s += 3;
  if (r.followUp) s += 1;
  if (r.nMis > 0 && r.nHedged === r.nMis) s += 3;   // 全部带"可能"措辞 ← 最关键
  else if (r.nHedged > 0) s += 1;
  if (r.ms < 8000) s += 2; else if (r.ms < 20000) s += 1;
  return { ...r, score: s };
}).sort((a, b) => b.score - a.score);

for (const r of scored) {
  const verdict = r.score < 0 ? '不可用' : r.score >= 11 ? '★ 推荐' : r.score >= 8 ? '可用' : '一般';
  console.log(`  ${String(r.score).padStart(3)} 分  ${r.model.padEnd(24)} ${verdict}${r.ok ? `  (${r.ms}ms, ${r.total ?? '?'} tokens)` : ''}`);
}
const best = scored.find((r) => r.score >= 8);
if (best) {
  console.log('\n  建议 GENAI_MODEL = ' + best.model);
  const others = scored.filter((r) => r.ok && r.model !== best.model).slice(0, 3).map((r) => r.model);
  if (others.length) console.log('  建议 GENAI_MODEL_FALLBACKS = ' + others.join(','));
} else {
  console.log('\n  没有模型达到可用标准，请检查端点或密钥。');
}
