#!/usr/bin/env node
/**
 * check-channels.mjs — 检查 FastGPT 里模型渠道的配置状态
 *
 * 用途：
 *   在界面里（账号 → 模型提供商）添加渠道之后，用它确认**真的生效了**。
 *   因为这一步是整个部署里唯一必须手工做的操作，做完容易不确定有没有成功。
 *
 * 判定依据：
 *   GET /api/core/ai/model/list 返回 { models: [...], providers: [...] }
 *   - providers：FastGPT 内置的提供商**定义**（37 个，与是否配置无关，永远是满的）
 *   - models   ：你**实际配置的模型渠道**（未配置时为 0）
 *   所以看 models 的长度就知道渠道有没有建好——只看 providers 会误判。
 *
 * 用法：
 *   node tools/check-channels.mjs
 *   node tools/check-channels.mjs --token <登录token>     # 不读缓存时手动指定
 *   node tools/check-channels.mjs --wait 60               # 轮询等待（秒），便于在界面操作后挂着等
 *
 * 说明：本脚本只做只读查询，不修改任何配置。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const TOKEN_FILE = path.join(ROOT, '.verify', 'root-token.txt');
const ENV_FILE = path.join(ROOT, 'env', '.env');

const argv = process.argv.slice(2);
const optVal = (n) => { const i = argv.indexOf(n); return i >= 0 ? argv[i + 1] || '' : ''; };

/* ---------------------------------------------------------------- 读取配置 */

function readEnv() {
  if (!fs.existsSync(ENV_FILE)) return {};
  const out = {};
  for (const line of fs.readFileSync(ENV_FILE, 'utf8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)$/);
    if (m) out[m[1]] = m[2].trim();
  }
  return out;
}

const env = readEnv();
const port = env.FASTGPT_HOST_PORT || '3100';
const BASE = `http://127.0.0.1:${port}`;

let token = optVal('--token');
if (!token && fs.existsSync(TOKEN_FILE)) {
  token = fs.readFileSync(TOKEN_FILE, 'utf8').trim();
}

/* ---------------------------------------------------------------- 登录兜底 */

/**
 * 缓存的 token 可能过期（有 TTL）。过期时用 env 里的 root 账号自动重新登录，
 * 免得用户还要手动去抓 token。
 */
async function login() {
  const user = env.DEFAULT_ROOT_USERNAME || 'root';
  const pwd = env.DEFAULT_ROOT_PSW;
  if (!pwd) return '';
  const crypto = await import('node:crypto');
  const sha256 = (s) => crypto.createHash('sha256').update(s).digest('hex');
  const pre = await fetch(`${BASE}/api/support/user/account/preLogin?username=${encodeURIComponent(user)}`);
  const preJ = await pre.json();
  const code = preJ?.data?.code;
  if (!code) return '';
  const r = await fetch(`${BASE}/api/support/user/account/loginByPassword`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: user, password: sha256(pwd), code })
  });
  const j = await r.json();
  const t = j?.data?.token || '';
  if (t) fs.writeFileSync(TOKEN_FILE, t);
  return t;
}

/* ---------------------------------------------------------------- 查询渠道 */

async function fetchChannels() {
  const r = await fetch(`${BASE}/api/core/ai/model/list`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (r.status === 401 || r.status === 403) return { needsLogin: true, status: r.status };
  if (r.status !== 200) return { error: `HTTP ${r.status}: ${(await r.text()).slice(0, 160)}` };
  const j = await r.json();
  const d = j.data || {};
  return { models: d.models || [], providers: d.providers || [] };
}

function report(res) {
  console.log('='.repeat(72));
  console.log(' FastGPT 模型渠道配置检查');
  console.log('='.repeat(72));
  console.log(`  地址: ${BASE}`);
  console.log(`  用时: ${new Date().toLocaleTimeString()}`);
  console.log('');

  if (res.error) {
    console.log('  ✗ 查询失败：' + res.error);
    console.log('    请确认 FastGPT 容器在运行：');
    console.log('      node tools/lab.ps1 status');
    return 2;
  }
  if (res.needsLogin) {
    console.log(`  ✗ 登录态失效（HTTP ${res.status}），且未能自动登录。`);
    console.log('    可在界面登录后手动传 token：node tools/check-channels.mjs --token <token>');
    return 3;
  }

  const { models, providers } = res;
  console.log(`  内置提供商定义: ${providers.length} 个（与是否配置无关，恒为满值）`);
  console.log(`  已配置的渠道  : ${models.length} 个   ← 关键指标`);
  console.log('');

  if (models.length === 0) {
    console.log('  ────────────────────────────────────────────────────────────');
    console.log('  渠道**尚未配置**。这是当前唯一剩下的手工步骤：');
    console.log('');
    console.log(`    1. 打开 ${BASE}，用 root + env/.env 里的 DEFAULT_ROOT_PSW 登录`);
    console.log('    2. 左下角头像 → 账号 → 模型提供商');
    console.log('    3. 新增一个 OpenAI 兼容渠道：');
    console.log(`         Base URL : ${env.GENAI_BASE_URL || '(见 env/.env 的 GENAI_BASE_URL)'}`);
    console.log('         API Key  : env/.env 里的 GENAI_API_KEY（不要贴到聊天里）');
    console.log(`         模型     : ${env.GENAI_MODEL || 'DeepSeek-V4-Flash'}`);
    if (env.GENAI_EMBEDDING_MODEL) {
      console.log(`         嵌入模型 : ${env.GENAI_EMBEDDING_MODEL}（维度 2048，供知识库用）`);
    }
    console.log('    4. 保存后点「测试」；然后重跑本脚本确认数字从 0 变成非 0');
    console.log('');
    console.log('  想挂着等界面操作完成，可用：node tools/check-channels.mjs --wait 120');
    console.log('  ────────────────────────────────────────────────────────────');
    return 1;
  }

  console.log('  ✓ 渠道已配置：');
  for (const m of models) {
    const name = m.model || m.name || m.id || '(无名)';
    const prov = m.provider || m.Provider || '';
    const types = [m.type].flat().filter(Boolean).join(',');
    console.log(`      · ${name}${prov ? `  [${prov}]` : ''}${types ? `  {${types}}` : ''}`);
  }
  console.log('');
  console.log('  下一步：按 fastgpt/WORKFLOW.md §10 创建高级编排应用');
  console.log('  （应用类型在接口枚举里叫 advanced，不是 workflow）');
  return 0;
}

/* ---------------------------------------------------------------- 主流程 */

let res = token ? await fetchChannels() : { needsLogin: true, status: 401 };
if (res.needsLogin) {
  console.log('  （登录态失效，尝试用 env/.env 的 root 账号自动登录…）');
  token = await login();
  res = token ? await fetchChannels() : { needsLogin: true, status: 401 };
}

const waitSec = Number(optVal('--wait') || 0);
if (waitSec > 0 && !res.error && !res.needsLogin && (res.models || []).length === 0) {
  console.log(`  轮询等待中（最多 ${waitSec} 秒，每 10 秒检查一次，Ctrl+C 可中断）…\n`);
  const deadline = Date.now() + waitSec * 1000;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 10000));
    const again = await fetchChannels();
    if (again.models && again.models.length > 0) { res = again; break; }
    process.stdout.write(`    ${new Date().toLocaleTimeString()} 仍是 0 个渠道…\r`);
  }
  console.log('');
}

process.exitCode = report(res);
