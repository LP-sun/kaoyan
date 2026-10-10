#!/usr/bin/env node
/**
 * set-genai.mjs — 配置 GenAI 提供方（上科大校方网关 / 并行科技 / 自定义）
 *
 * 为什么需要这个脚本：
 *   上科大网关**不是**标准的 OpenAI 路径。它的 Base URL 必须填到
 *   `/api/v1/start`，由 OpenAI SDK 自动补 `/chat/completions`，
 *   最终请求 `/api/v1/start/chat/completions`。
 *   如果按常规只填 `.../api/v1`，请求会打到 `/api/v1/chat/completions` 并返回 404。
 *   这是一个很容易踩、且报错信息（404）完全指不出原因的坑。
 *   （我本人就先踩了这个坑：用错误的路径 + 错误的 key 探测，
 *     得到 401「错误的api-key」，据此误判"网关未打通"。）
 *
 * 用法：
 *   node tools/set-genai.mjs school              # 上科大网关（凭据取 DSH 本机凭据库）
 *   node tools/set-genai.mjs paratera            # 并行科技
 *   node tools/set-genai.mjs custom <base> <model> [key]
 *   node tools/set-genai.mjs show                # 只显示当前配置（不打印密钥值）
 *   node tools/set-genai.mjs test [school|paratera]   # 只测连通性，不写 .env
 *
 * 可选开关：
 *   --key <KEY>     显式指定密钥（不推荐：会留在命令历史里）
 *   --key-stdin     从标准输入读密钥（比 --key 安全）
 *   --model <ID>    覆盖模型 ID
 *   --no-backup     不生成 .env.bak
 *   --force         连通性测试失败也照写（默认失败即中止，不写入坏配置）
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ENV_FILE = path.join(ROOT, 'env', '.env');
const CRED_FILE = path.join(os.homedir(), '.dsh', '.credentials.yaml');

/* ------------------------------------------------------------------ 提供方定义 */

const PROVIDERS = {
  /*
   * 上科大校方网关。
   * base 里的 /api/v1/start 是**必须的**，不是笔误：
   * OpenAI SDK 会在 base 后面补 /chat/completions，
   * 于是最终请求 /api/v1/start/chat/completions —— 这才是学校真实端点。
   */
  school: {
    label: '上海科技大学 GenAI',
    baseUrl: 'https://genaiapi.shanghaitech.edu.cn/api/v1/start',
    model: 'deepseek-v4-pro',
    fallbacks: 'DeepSeek-V4-Pro',
    embedding: '',
    timeout: '60',
    retries: '2',
    // 凭据来源：DSH 本机凭据库的 DEEPSEEK_API_KEY
    credKeys: ['DEEPSEEK_API_KEY'],
    noEmbedding: true,   // 见 notes：该网关不提供嵌入接口
    notes: [
      '请求路径 = /api/v1/start/chat/completions（SDK 自动补 /chat/completions）',
      '已验证可用模型：deepseek-v4-pro、DeepSeek-V4-Pro（服务端实际名为 deepseek-pro）',
      '无权限模型：deepseek-chat 返回 403「该模型无使用权限」',
      '首次调用可能超过 30 秒（冷启动），属正常现象，故超时设为 60s',
      '注意 1：该网关**不提供嵌入(embeddings)接口**，请求 /embeddings 会被路由到',
      '        /chat/completions 并报缺 messages。故 GENAI_EMBEDDING_MODEL 留空，',
      '        FastGPT 的知识库向量检索将不可用（对话与工作流不受影响）。',
      '注意 2：实测传入 qwen3-max / glm-4-plus 等其它模型名，返回的 model 仍是',
      '        deepseek-pro ——说明网关统一路由，模型名基本不起作用，不必纠结模型 ID。',
      '注意 3：该网关无模型列表接口（/start/models 返回 405，/api/v1/models 返回 404），',
      '        因此 tools/survey-models.mjs 对它无效，这是正常的，不代表配置错误。'
    ]
  },

  /*
   * 并行科技（当前生产在用）。标准 OpenAI 路径，与 vLLM/LiteLLM 兼容。
   * 模型经真实工作流同构基准评测选出，见 FASTGPT_DEPLOY_REPORT.md §9。
   */
  paratera: {
    label: '并行科技 MaaS',
    baseUrl: 'https://llmapi.paratera.com/v1',
    model: 'DeepSeek-V4-Flash',
    fallbacks: 'DeepSeek-V4.1-Flash,Kimi-K2.6,Qwen3.8-Flash',
    embedding: 'GLM-Embedding-3',
    timeout: '60',
    retries: '2',
    credKeys: ['PARATERA_API_KEY', 'DEEPSEEK_API_KEY'],
    notes: [
      '标准 OpenAI 路径：请求 /v1/chat/completions',
      '主模型 DeepSeek-V4-Flash：评测 12 分 / 5.4s / 1元输入+2元输出 每百万 token',
      '嵌入模型 GLM-Embedding-3（2048 维），供 FastGPT 知识库使用',
      '注意：DeepSeek-V3.2 / V3.1 / GPT-5.6-Luna 虽在列表中但账户渠道受限（503）'
    ]
  }
};

/* ------------------------------------------------------------------ 工具函数 */

const argv = process.argv.slice(2);
const flag = (n) => argv.includes(n);
const optVal = (n) => {
  const i = argv.indexOf(n);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : '';
};
/*
 * 解析位置参数（非选项值）。
 * 注意选项的“值”也算在 argv 里，必须跳过，
 * 否则 `--model X` 里的 X 会被误当成位置参数。
 */
const VALUE_OPTS = new Set(['--key', '--model']);
const positional = [];
for (let i = 0; i < argv.length; i += 1) {
  const a = argv[i];
  if (VALUE_OPTS.has(a)) { i += 1; continue; }   // 跳过选项及其值
  if (a.startsWith('--')) continue;              // 跳过布尔开关
  positional.push(a);
}

function readEnvFile() {
  if (!fs.existsSync(ENV_FILE)) return {};
  const out = {};
  for (const line of fs.readFileSync(ENV_FILE, 'utf8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)$/);
    if (m) out[m[1]] = m[2].trim();
  }
  return out;
}

/** 从 DSH 本机凭据库按优先级找密钥。只返回值，绝不打印。 */
function readCredential(keys) {
  if (!fs.existsSync(CRED_FILE)) return { key: '', from: '' };
  const text = fs.readFileSync(CRED_FILE, 'utf8');
  for (const k of keys) {
    const m = text.match(new RegExp('^\\s*' + k + ':\\s*(.+?)\\s*$', 'm'));
    if (m) {
      const v = m[1].replace(/^["']|["']$/g, '');
      if (v) return { key: v, from: `凭据库 ${k}` };
    }
  }
  return { key: '', from: '' };
}

/** 从标准输入读密钥（避免留在命令历史） */
async function readStdin() {
  const chunks = [];
  for await (const c of process.stdin) chunks.push(c);
  return Buffer.concat(chunks).toString('utf8').trim();
}

/** 只显示末四位，用于人工核对是不是同一把钥匙 */
const mask = (k) => (k ? `${k.length} 字符，末四位 ****${k.slice(-4)}` : '（空）');

/* ------------------------------------------------------------------ 连通性测试 */

async function testProvider(base, key, model) {
  const url = base.replace(/\/+$/, '') + '/chat/completions';
  const t0 = Date.now();
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 90000);
  try {
    const r = await fetch(url, {
      method: 'POST',
      signal: ctl.signal,
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + key },
      // max_tokens 给足：带思维链的模型会先输出 reasoning_content，
      // 而思维链同样计入配额，配额太小会导致空响应（见报告 §9.2）
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: '只回答两个字：收到' }],
        max_tokens: 600,
        temperature: 0
      })
    });
    const raw = await r.text();
    const ms = Date.now() - t0;
    if (r.status === 200) {
      let content = '', servedModel = '';
      try {
        const j = JSON.parse(raw);
        content = (j.choices?.[0]?.message?.content || '').trim();
        servedModel = j.model || '';
      } catch { /* 忽略 */ }
      // 不把 key 回显到任何输出里
      return { ok: true, ms, content, servedModel, status: 200 };
    }
    // 从错误体里提取有用信息；顺带确保不泄漏 key
    let msg = '';
    try {
      const j = JSON.parse(raw);
      msg = j?.error?.message || j?.message || '';
    } catch { msg = raw.replace(/\s+/g, ' ').slice(0, 120); }
    if (key) msg = msg.split(key).join('<KEY>');
    return { ok: false, ms, status: r.status, msg };
  } catch (e) {
    return { ok: false, ms: Date.now() - t0, status: 0, msg: e.name + ': ' + e.message };
  } finally {
    clearTimeout(timer);
  }
}

/* ------------------------------------------------------------------ 写 .env */

function writeEnv(patch, { backup = true } = {}) {
  if (!fs.existsSync(ENV_FILE)) {
    console.error(`  找不到 ${ENV_FILE}`);
    console.error('  请先：Copy-Item env\\.env.example env\\.env');
    process.exit(1);
  }
  const original = fs.readFileSync(ENV_FILE, 'utf8');
  if (backup) {
    fs.writeFileSync(ENV_FILE + '.bak', original);
  }
  const lines = original.split(/\r?\n/);
  const seen = new Set();
  const out = lines.map((line) => {
    const m = line.match(/^(\s*)([A-Z0-9_]+)(\s*)=/);
    if (!m) return line;
    const k = m[2];
    if (!(k in patch)) return line;
    seen.add(k);
    return `${k}=${patch[k]}`;
  });
  // 如果某个键原本不存在（例如被注释掉），追加到末尾
  const missing = Object.keys(patch).filter((k) => !seen.has(k));
  if (missing.length) {
    out.push('');
    out.push('# 由 tools/set-genai.mjs 追加');
    for (const k of missing) out.push(`${k}=${patch[k]}`);
  }
  fs.writeFileSync(ENV_FILE, out.join('\n'));
  return { backupPath: backup ? ENV_FILE + '.bak' : null, added: missing };
}

/* ------------------------------------------------------------------ 主流程 */

const cmd = positional[0] || 'show';

if (cmd === 'show') {
  const env = readEnvFile();
  console.log('='.repeat(70));
  console.log(' 当前 GenAI 配置（不打印密钥值）');
  console.log('='.repeat(70));
  console.log('  配置文件   : ' + ENV_FILE);
  console.log('  BASE_URL   : ' + (env.GENAI_BASE_URL || '（未设置）'));
  console.log('  模型       : ' + (env.GENAI_MODEL || '（未设置）'));
  console.log('  备用模型   : ' + (env.GENAI_MODEL_FALLBACKS || '（未设置）'));
  console.log('  嵌入模型   : ' + (env.GENAI_EMBEDDING_MODEL || '（未设置）'));
  console.log('  API_KEY    : ' + mask(env.GENAI_API_KEY));
  const host = (env.GENAI_BASE_URL || '').replace(/^https?:\/\//, '').split('/')[0];
  const which = host.includes('shanghaitech') ? '学校网关' : host.includes('paratera') ? '并行科技' : '自定义';
  console.log('  识别为     : ' + which);
  process.exit(0);
}

// 解析目标提供方
let target = null;
let customKey = '';   // custom 允许把 key 作为位置参数传入
if (cmd === 'custom') {
  const base = positional[1];
  const model = positional[2];
  if (!base || !model) {
    console.error('用法: node tools/set-genai.mjs custom <BASE_URL> <MODEL_ID> [API_KEY]');
    process.exit(2);
  }
  target = {
    label: '自定义',
    baseUrl: base,
    model,
    fallbacks: '',
    embedding: '',
    timeout: '60',
    retries: '2',
    credKeys: [],
    notes: ['自定义端点：请自行确认路径约定（是否需要 /v1 或 /api/v1/start 之类前缀）']
  };
  if (positional[3]) customKey = positional[3];
} else if (PROVIDERS[cmd]) {
  target = PROVIDERS[cmd];
} else if (cmd === 'test' && PROVIDERS[positional[1]]) {
  target = PROVIDERS[positional[1]];
} else {
  console.error('未知目标: ' + cmd);
  console.error('可用: school | paratera | custom <base> <model> | show | test <school|paratera>');
  process.exit(2);
}

/* --- 决定密钥 --- */
const env = readEnvFile();
let key = optVal('--key') || customKey;
let keyFrom = key ? '命令行参数' : '';
if (flag('--key-stdin')) {
  key = await readStdin();
  keyFrom = '标准输入';
}
if (!key) {
  // 先看现有 .env：如果切换的是同一个 host，沿用原 key 最省事
  const sameHost = (env.GENAI_BASE_URL || '').replace(/^https?:\/\//, '').split('/')[0]
                === target.baseUrl.replace(/^https?:\/\//, '').split('/')[0];
  if (sameHost && env.GENAI_API_KEY) {
    key = env.GENAI_API_KEY;
    keyFrom = '现有 env/.env（同 host，沿用）';
  }
}
if (!key && target.credKeys.length) {
  const c = readCredential(target.credKeys);
  if (c.key) { key = c.key; keyFrom = c.from; }
}

console.log('='.repeat(70));
console.log(` 目标: ${target.label}`);
console.log('='.repeat(70));
console.log('  BASE_URL   : ' + target.baseUrl);
console.log('  模型       : ' + target.model);
console.log('  API_KEY    : ' + mask(key) + (keyFrom ? `  ← 来源: ${keyFrom}` : ''));
for (const n of target.notes) console.log('  · ' + n);

if (!key) {
  console.error('\n  没有拿到 API Key。可选其一：');
  console.error('    1) echo <KEY> | node tools/set-genai.mjs ' + cmd + ' --key-stdin');
  console.error('    2) 先在 env/.env 里填好 GENAI_API_KEY，再运行本脚本');
  if (target.credKeys.length) {
    console.error(`    3) 把 ${target.credKeys[0]} 写入 ${CRED_FILE}`);
  }
  process.exit(3);
}

/* --- 连通性测试 --- */
console.log('\n[1/2] 连通性测试（真实调用一次，max_tokens=600）...');
const r = await testProvider(target.baseUrl, key, target.model);
if (r.ok) {
  console.log(`  ✓ HTTP 200  ${r.ms}ms`);
  console.log(`    实际请求 : ${target.baseUrl.replace(/\/+$/, '')}/chat/completions`);
  console.log(`    模型回答 : "${r.content.slice(0, 40)}"`);
  if (r.servedModel) console.log(`    服务端模型名: ${r.servedModel}`);
  if (r.ms > 15000) console.log('    ! 响应较慢（学校网关冷启动可能超过 30s），属正常现象');
} else {
  console.log(`  ✗ 失败  HTTP ${r.status}  ${r.ms}ms`);
  console.log('    ' + r.msg);
  console.log('\n  排查提示：');
  if (r.status === 401) {
    console.log('    · 401 = 密钥无效或未授权。确认用的是**该提供方**自己的 key。');
    console.log('      注意：拿 A 家的 key 打 B 家的端点必然 401，这不代表端点不可用。');
  } else if (r.status === 403) {
    console.log('    · 403 = 密钥有效但该模型无权限。换一个模型 ID（如 deepseek-v4-pro）。');
  } else if (r.status === 404) {
    console.log('    · 404 = 路径不对。检查 BASE_URL 前缀：');
    console.log('      学校网关需要 /api/v1/start（SDK 自动补 /chat/completions）');
    console.log('      并行科技需要 /v1');
  }
  if (!flag('--force')) {
    console.log('\n  未写入 .env（连通性不通过时不写入坏配置）。加 --force 可强制写入。');
    process.exit(4);
  }
  console.log('\n  --force 已指定，仍将写入配置。');
}

/*
 * test 子命令：只测连通性，**不得写入** .env。
 * 这里必须提前返回——早期版本漏了这个分支，
 * 导致 `test school` 在测完后继续走写入流程、把正在使用的配置覆盖掉了。
 */
if (cmd === 'test') {
  console.log('\n（test 模式：仅测试连通性，未修改 env/.env）');
  /*
   * 必须在这里真正终止进程。
   * 踩过的坑：先前写成 `process.exitCode = ...` 想避免 libuv 的
   * "Assertion failed: !(handle->flags & UV_HANDLE_CLOSING)" 噪音，
   * 但 exitCode **只设置退出码、不会停止执行**，于是脚本继续往下走并
   * 覆盖了 env/.env —— 与 "只测不写" 的承诺相反，且真的把正在使用的配置改掉了。
   * 现在改成显式 exit()，并把这段放在写入之前。
   */
  process.exit(r.ok ? 0 : 5);
}

/* --- 写入 .env --- */
console.log('\n[2/2] 写入 env/.env ...');
const patch = {
  GENAI_BASE_URL: target.baseUrl,
  GENAI_API_KEY: key,
  GENAI_MODEL: optVal('--model') || target.model,
  GENAI_MODEL_FALLBACKS: target.fallbacks,
  GENAI_EMBEDDING_MODEL: target.embedding
};
if (target.timeout) patch.GENAI_TIMEOUT = target.timeout;
if (target.retries) patch.GENAI_MAX_RETRIES = target.retries;
const res = writeEnv(patch, { backup: !flag('--no-backup') });
console.log('  ✓ 已写入' + (res.backupPath ? `（原文件备份为 ${path.basename(res.backupPath)}）` : '（未备份）'));
if (res.added.length) console.log('  新增键: ' + res.added.join(', '));

if (target.noEmbedding) {
  console.log('\n  ⚠ 重要：该提供方不支持嵌入模型，GENAI_EMBEDDING_MODEL 已置空。');
  console.log('    FastGPT 的**知识库向量检索将不可用**（需在界面里选择 LLM 模式的知识库，');
  console.log('    或不用知识库）。对话与工作流功能不受影响。');
  console.log('    如果需要知识库，请用：node tools/set-genai.mjs paratera');
}

console.log('\n完成。下一步：');
console.log('  node tools/genai-conntest.mjs        # 7 步连通性检查');
if (cmd === 'school') {
  console.log('  （跳过 survey-models.mjs：学校网关无 /models 端点，跑了必然失败，属正常）');
}
console.log('  重启诊断服务以生效：先结束旧 node 进程，再 node tools/diagnosis-server.mjs');
console.log('\n切换到其它提供方：node tools/set-genai.mjs paratera');
