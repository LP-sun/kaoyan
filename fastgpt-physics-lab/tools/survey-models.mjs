#!/usr/bin/env node
/**
 * survey-models.mjs — 模型可用性普查
 *
 * 背景：并行科技的 /v1/models 返回 101 个模型，但账户有"渠道限制"，
 * 部分模型实际返回 503「当前用户模型渠道限制下无可用渠道」。
 * 因此"列表里有"≠"你能用"。本脚本把这件事查清楚。
 *
 * 对每个模型发一个最小请求，记录：
 *   ok       可用
 *   blocked  503 渠道限制（账户无权限）
 *   other    其他错误
 *
 * 用法：
 *   node tools/survey-models.mjs                # 普查内置的常用候选集
 *   node tools/survey-models.mjs --all          # 普查 .verify/models.json 里全部 101 个
 *   node tools/survey-models.mjs --raw GLM-4.6  # 打印某模型的原始响应（排查为何不是 JSON）
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const txt = fs.readFileSync(path.join(ROOT, 'env', '.env'), 'utf8');
const pick = (k) => { const m = txt.match(new RegExp('^' + k + '=(.*)$', 'm')); return m ? m[1].trim() : ''; };
const BASE = pick('GENAI_BASE_URL').replace(/\/+$/, '');
const KEY = pick('GENAI_API_KEY');
const mask = (s) => String(s).split(KEY).join('<KEY>');

const rawIdx = process.argv.indexOf('--raw');
if (rawIdx > -1) {
  const model = process.argv[rawIdx + 1];
  const r = await fetch(`${BASE}/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${KEY}` },
    body: JSON.stringify({
      model,
      messages: [
        { role: 'system', content: '只输出 JSON，不要 markdown 代码块。格式：{"a":1}' },
        { role: 'user', content: '输出 {"a":1}' }
      ],
      temperature: 0
    })
  });
  console.log('HTTP ' + r.status);
  console.log(mask(await r.text()));
  process.exit(0);
}

const CANDIDATES = [
  // 中文/物理推理较强的常用候选
  'Qwen3.8-Max', 'Qwen3.8-Flash', 'Qwen3.7-Max', 'Qwen3.7-Plus', 'Qwen3.6-Plus', 'Qwen3.6-Flash',
  'GLM-5.3', 'GLM-5.3-Flash', 'GLM-5.2', 'GLM-4.7', 'GLM-4.6', 'GLM-4.5', 'GLM-4.5-Flash',
  'Kimi-K3', 'Kimi-K2.6', 'MiniMax-M3', 'MiniMax-M2.7',
  'DeepSeek-V4.1-Flash', 'DeepSeek-V4-Flash', 'DeepSeek-V3.2', 'DeepSeek-V3.1',
  'ERNIE-5.0-Thinking-Preview', 'Intern-S2-Preview',
  'GPT-5.6-Luna', 'GPT-6-Astra', 'AZ-GPT-5.6-Luna',
  'Baichuan-M3'
];

let models = CANDIDATES;
if (process.argv.includes('--all')) {
  const p = path.join(ROOT, '.verify', 'models.json');
  if (fs.existsSync(p)) {
    // 只测对话类，跳过明显的图像/视频/语音/OCR 模型
    models = JSON.parse(fs.readFileSync(p, 'utf8')).filter(
      (m) => !/Seedance|Seedream|T2I|I2V|T2V|Image|CogView|WanX|ASR|OCR|Hailuo|Rerank|Embedding/i.test(m)
    );
  }
}

console.log('='.repeat(76));
console.log(' 模型可用性普查  （共 ' + models.length + ' 个候选）');
console.log(' 端点: ' + BASE);
console.log('='.repeat(76));

async function probe(model) {
  const t0 = Date.now();
  try {
    const c = new AbortController();
    const t = setTimeout(() => c.abort(), 45000);
    const r = await fetch(`${BASE}/chat/completions`, {
      method: 'POST',
      signal: c.signal,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${KEY}` },
      body: JSON.stringify({ model, messages: [{ role: 'user', content: '回复：ok' }], max_tokens: 8, temperature: 0 })
    });
    clearTimeout(t);
    const raw = await r.text();
    const ms = Date.now() - t0;
    if (r.status === 200) return { model, state: 'ok', ms };
    const msg = mask(raw).replace(/\s+/g, ' ').slice(0, 110);
    if (/渠道限制|无可用渠道|ServiceUnavailable/i.test(raw)) return { model, state: 'blocked', ms, msg };
    return { model, state: 'other', ms, msg: `HTTP ${r.status} ${msg}` };
  } catch (e) {
    return { model, state: 'other', ms: Date.now() - t0, msg: e.message };
  }
}

const out = [];
for (const m of models) {
  const r = await probe(m);
  out.push(r);
  const icon = r.state === 'ok' ? '✓' : r.state === 'blocked' ? '⛔' : '✗';
  const note = r.state === 'ok' ? `${r.ms}ms` : r.msg;
  console.log(`  ${icon}  ${m.padEnd(28)} ${note}`);
}

const ok = out.filter((r) => r.state === 'ok');
const blocked = out.filter((r) => r.state === 'blocked');
console.log('\n' + '='.repeat(76));
console.log(` 可用 ${ok.length} 个 | 渠道限制 ${blocked.length} 个 | 其他错误 ${out.length - ok.length - blocked.length} 个`);
console.log('='.repeat(76));
console.log('\n  ★ 账户实际可用的对话模型：');
for (const r of ok) console.log(`      ${r.model.padEnd(28)} ${r.ms}ms`);
if (blocked.length) {
  console.log('\n  ⛔ 被账户渠道限制的模型（列表里有但你用不了）：');
  console.log('      ' + blocked.map((r) => r.model).join(', '));
}
fs.writeFileSync(path.join(ROOT, '.verify', 'models-usable.json'), JSON.stringify(ok.map((r) => r.model), null, 2), 'utf8');
console.log('\n  可用清单已保存到 .verify/models-usable.json');
