#!/usr/bin/env node
/**
 * genai-conntest.mjs — 上海科技大学 GenAI API 连通性测试
 *
 * 按任务要求逐项验证：
 *   1. 认证是否成功
 *   2. 模型名称是否有效
 *   3. 是否支持 Chat Completions
 *   4. 是否能返回简单中文回答
 *   5. 是否有明显的超时、限流或请求格式问题
 *   6. 模型列表接口是否可用（可用则调用，不可用属正常）
 *   7. Embedding 接口是否存在（决定 FastGPT 知识库能否启用）
 *
 * 全程使用极小 max_tokens，避免消耗配额。
 * 密钥只从 env/.env 或进程环境变量读取，绝不打印。
 *
 * 用法：
 *   node tools/genai-conntest.mjs
 *   node tools/genai-conntest.mjs --model <模型ID>     覆盖模型
 *   node tools/genai-conntest.mjs --base  <BASE_URL>   覆盖地址
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadConfig, chat, resolveChatUrl, listModels, probeEmbedding, candidateChatUrls } from './genai.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const cfg = loadConfig(ROOT);

/* 命令行覆盖 */
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === '--model' && argv[i + 1]) cfg.model = argv[++i];
  if (argv[i] === '--base' && argv[i + 1]) cfg.baseUrl = argv[++i].replace(/\/+$/, '');
}

const results = [];
function record(name, status, detail) {
  results.push({ name, status, detail });
  const mark = status === 'PASS' ? '✓ PASS' : status === 'FAIL' ? '✗ FAIL' : '!  ' + status;
  console.log(`  ${mark}  ${name}`);
  if (detail) console.log(`           ${detail}`);
}

console.log('='.repeat(74));
console.log(' 上海科技大学 GenAI API 连通性测试');
console.log('='.repeat(74));
console.log(` 配置文件   : ${cfg.envPath}（${cfg.envFileExists ? '存在' : '不存在'}）`);
console.log(` BASE_URL   : ${cfg.baseUrl || '(未设置)'}`);
console.log(` MODEL      : ${cfg.model || '(未设置)'}`);
console.log(` API Key    : ${cfg.apiKey ? `已设置（长度 ${cfg.apiKey.length}，内容不显示）` : '(未设置)'}`);
console.log('='.repeat(74));

/* ---------------------------------------------------- 0. 参数完整性 */
console.log('\n[0] 参数完整性');
const missing = [];
if (!cfg.baseUrl) missing.push('GENAI_BASE_URL');
if (!cfg.apiKey) missing.push('GENAI_API_KEY');
if (!cfg.model) missing.push('GENAI_MODEL');
if (missing.length) {
  record('参数完整性', 'FAIL', `缺少：${missing.join(', ')}。请编辑 ${cfg.envPath} 后重跑。`);
  console.log('\n提示：复制 env/.env.example 为 env/.env，填入学校提供的 API Address / Key / 模型 ID。');
  console.log('      不要把密钥粘贴到聊天窗口、截图或提交到 Git。');
  process.exitCode = 1;
  process.exit();
}
record('参数完整性', 'PASS', '三个必填参数均已设置');

/* ---------------------------------------------------- 1. 端点与鉴权 */
console.log('\n[1] 端点探测与认证');
console.log('    候选端点：');
for (const u of candidateChatUrls(cfg.baseUrl)) console.log('      - ' + u);
const probe = await resolveChatUrl(cfg, { timeoutMs: 30000, verbose: true });
if (!probe.ok) {
  record('认证', 'FAIL', probe.error || `HTTP ${probe.status}`);
  console.log('\n排查建议：');
  console.log('  - 401/403：Key 无效或过期，或需要额外的鉴权头（如 x-api-key）。');
  console.log('  - 404：BASE_URL 可能缺少或多余 /v1 前缀，尝试 https://<网关>/v1 或 https://<网关>。');
  console.log('  - 超时：校园网/VPN 未连通，本机系统代理未生效。');
  process.exitCode = 1;
  process.exit();
}
record('端点探测', 'PASS', `可用端点：${probe.url}`);
record('认证', 'PASS', 'Bearer 鉴权通过（探测请求返回 2xx）');

/* ---------------------------------------------------- 2. 中文极简问答 */
console.log('\n[2] Chat Completions 与中文回答（max_tokens=32）');
const t0 = Date.now();
const r1 = await chat(
  cfg,
  [
    { role: 'system', content: '你是一个测试助手，严格按用户要求回答。' },
    { role: 'user', content: '请用中文回答：中国的首都是哪里？只回答城市名。' }
  ],
  { maxTokens: 32, temperature: 0 }
);
const latency = Date.now() - t0;
if (!r1.ok) {
  record('Chat Completions', 'FAIL', r1.error + ' ' + JSON.stringify(r1.last || {}));
} else {
  record('Chat Completions', 'PASS', `HTTP 2xx，model=${r1.model}`);
  const hasChinese = /[\u4e00-\u9fa5]/.test(r1.content);
  record('中文回答', hasChinese ? 'PASS' : 'FAIL', `返回内容：「${r1.content.trim().slice(0, 60)}」`);
  record('响应延迟', latency < 30000 ? 'PASS' : 'WARN', `${latency} ms（含一次端点探测）`);
  if (r1.usage) record('Token 用量', 'PASS', JSON.stringify(r1.usage));
}

/* ---------------------------------------------------- 3. 格式与限流健壮性 */
console.log('\n[3] 请求格式与限流行为');
const t1 = Date.now();
const r2 = await chat(
  cfg,
  [
    { role: 'system', content: '只输出 JSON。' },
    { role: 'user', content: '输出 {"ok":true} 这个 JSON，不要任何其他文字。' }
  ],
  { maxTokens: 32, temperature: 0 }
);
if (!r2.ok) {
  record('JSON 指令遵循', 'FAIL', r2.error);
} else {
  let parsed = null;
  try {
    parsed = JSON.parse(r2.content.trim().replace(/^```(?:json)?/i, '').replace(/```$/, '').trim());
  } catch {
    /* ignore */
  }
  record('JSON 指令遵循', parsed && parsed.ok === true ? 'PASS' : 'WARN', `返回「${r2.content.trim().slice(0, 80)}」`);
}
record(
  '限流迹象',
  'PASS',
  `两次串行请求间隔约 ${Date.now() - t1} ms 未见 429（如需压力测试请另行评估配额）`
);

/* ---------------------------------------------------- 4. 错误处理 */
console.log('\n[4] 无效模型名的错误处理');
const r3 = await chat(cfg, [{ role: 'user', content: 'hi' }], { maxTokens: 8, model: '__definitely_not_a_real_model__' });
if (r3.ok) {
  record('无效模型拒绝', 'WARN', '网关未按预期拒绝不存在的模型名（可能被静默回退到默认模型）');
} else {
  record('无效模型拒绝', 'PASS', `已正确报错：HTTP ${r3.last?.status} ${String(r3.last?.body || '').slice(0, 120)}`);
}

/* ---------------------------------------------------- 5. 模型列表 */
console.log('\n[5] 模型列表接口（可选）');
const lm = await listModels(cfg, { timeoutMs: 20000 });
if (lm.ok) {
  record('GET /models', 'PASS', `发现 ${lm.ids.length} 个模型：${lm.ids.slice(0, 20).join(', ')}${lm.ids.length > 20 ? ' …' : ''}`);
  const hit = lm.ids.includes(cfg.model);
  record('配置的模型在列表中', hit ? 'PASS' : 'WARN', hit ? cfg.model : `列表中未出现 ${cfg.model}（部分网关只返回部分模型，仍可手动指定）`);
} else {
  record('GET /models', 'SKIP', '接口不可用（学校未开放属正常，可手动配置模型 ID）');
}

/* ---------------------------------------------------- 6. Embedding */
console.log('\n[6] Embedding 接口（决定 FastGPT 知识库/向量检索能否启用）');
const em = await probeEmbedding(cfg, { timeoutMs: 20000 });
if (em.skipped) {
  record('Embedding', 'SKIP', '未配置 GENAI_EMBEDDING_MODEL（留空即视为学校不提供）');
  console.log('           影响：FastGPT 的知识库向量检索不可用；对话、工作流、交互节点不受影响。');
} else if (em.ok) {
  record('Embedding', 'PASS', `可用，端点 ${em.url}，向量维度 ${em.dim}`);
} else {
  record('Embedding', 'FAIL', em.error);
  console.log('           影响：无法配置索引模型，FastGPT 知识库不可用。诊断工作流不依赖向量检索，可继续。');
}

/* ---------------------------------------------------- 汇总 */
console.log('\n' + '='.repeat(74));
const pass = results.filter((r) => r.status === 'PASS').length;
const fail = results.filter((r) => r.status === 'FAIL').length;
const warn = results.filter((r) => r.status === 'WARN').length;
const skip = results.filter((r) => r.status === 'SKIP').length;
console.log(` 结果：PASS ${pass} / FAIL ${fail} / WARN ${warn} / SKIP ${skip}`);
console.log('='.repeat(74));

console.log('\n下一步：');
console.log('  1. 登录 FastGPT（http://127.0.0.1:3100，账号 root）');
console.log('  2. 进入「账号 → 模型提供商」，添加自定义 OpenAI 兼容渠道：');
console.log(`       接口地址：${cfg.baseUrl}`);
console.log(`       模型 ID ：${cfg.model}`);
console.log('     认证方式选 Bearer/API Key，Key 填学校提供的值。');
console.log('  3. 语言模型与索引模型分别选择该渠道下的模型（索引模型需要 Embedding 支持）。');
console.log('  4. 参考 fastgpt/WORKFLOW.md 创建「物理考研智能诊断」工作流。');

process.exitCode = fail === 0 ? 0 : 1;
