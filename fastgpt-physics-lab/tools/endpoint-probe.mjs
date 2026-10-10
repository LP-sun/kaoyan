#!/usr/bin/env node
/**
 * endpoint-probe.mjs — 端点探测与模型发现
 *
 * 用途：你手上有一个 API 地址和一个 Key，但不确定：
 *   1. BASE_URL 要不要带 /v1
 *   2. 该网关支持哪些模型 ID
 *   3. Key 是否有效
 * 这个脚本会把这些一次性问清楚。
 *
 * 它只做**只读**的探测请求（GET /models，以及可选的最小 chat 调用），
 * 不会打印密钥内容，也不会把密钥写入任何文件。
 *
 * 用法（密钥放在环境变量里，不要写在命令行历史里）：
 *
 *   # Windows PowerShell
 *   $env:PROBE_KEY="你的key"
 *   node tools/endpoint-probe.mjs https://llmapi.paratera.com/v1
 *
 *   # 只探测端点形态、不校验密钥（不带 key 也能看到 401/404 区别）
 *   node tools/endpoint-probe.mjs https://genai.shanghaitech.edu.cn
 *
 * 判定依据：
 *   401 + JSON 错误体  → 端点存在且是 API，只是缺/错密钥（**这是好信号**）
 *   200 + JSON         → 端点可用，若有 data[] 就能看到模型 ID 列表
 *   200 + HTML         → 这是前端网页，不是 API 端点（说明这个路径不对）
 *   404                → 该路径不存在
 */

const base = (process.argv[2] || '').replace(/\/+$/, '');
const key = process.env.PROBE_KEY || '';
const doChat = process.argv.includes('--chat');

if (!base) {
  console.error('用法: node tools/endpoint-probe.mjs <BASE_URL> [--chat]');
  console.error('示例: node tools/endpoint-probe.mjs https://llmapi.paratera.com/v1');
  process.exit(2);
}

function redact(s) {
  if (!key) return s;
  return String(s).split(key).join('<KEY>');
}

function authHeaders() {
  const h = { 'User-Agent': 'fastgpt-physics-lab/probe', Accept: 'application/json' };
  if (key) h.Authorization = `Bearer ${key}`;
  return h;
}

async function probe(url, init = {}) {
  const started = Date.now();
  try {
    const c = new AbortController();
    const t = setTimeout(() => c.abort(), 15000);
    const r = await fetch(url, { ...init, signal: c.signal, headers: { ...authHeaders(), ...(init.headers || {}) } });
    clearTimeout(t);
    const raw = await r.text();
    const ms = Date.now() - started;
    const isHtml = /^\s*<!DOCTYPE html|<html/i.test(raw);
    return { ok: true, status: r.status, raw, isHtml, ms, ct: r.headers.get('content-type') || '' };
  } catch (e) {
    return { ok: false, err: e.message };
  }
}

function classify(res) {
  if (!res.ok) return `连接失败: ${res.err}`;
  if (res.isHtml) return 'HTML 页面（前端网页，不是 API 端点）';
  if (res.status === 401 || res.status === 403) return '需要鉴权（端点存在，密钥缺失或无效）← API 端点的典型信号';
  if (res.status === 404) return '路径不存在';
  if (res.status === 405) return '方法不允许（把 GET 换成 POST 试试）';
  if (res.status === 200) return '可用';
  return `HTTP ${res.status}`;
}

console.log('='.repeat(74));
console.log(' 端点探测: ' + base);
console.log(' 密钥: ' + (key ? `已提供（长度 ${key.length}，内容不显示）` : '未提供（只能看端点形态，不能校验密钥）'));
console.log('='.repeat(74));

/* --------------------------------------------- 1. 端点形态 */
const candidates = [
  `${base}/models`,
  `${base}/chat/completions`,
  `${base}/embeddings`
];
// 若 base 已含 /v1，额外试一下"去掉 /v1"
if (/\/v1$/.test(base)) candidates.push(`${base.replace(/\/v1$/, '')}/models`);

console.log('\n[1] 端点形态（GET）');
for (const u of candidates) {
  const r = await probe(u);
  console.log(`  ${u}`);
  console.log(`      ${classify(r)}${r.ok ? `  [HTTP ${r.status}, ${r.ms}ms]` : ''}`);
  if (r.ok && !r.isHtml && r.raw) {
    const preview = r.raw.slice(0, 300).replace(/\s+/g, ' ');
    console.log('      响应片段: ' + redact(preview));
  }
  if (r.ok && r.isHtml) {
    console.log('      → 该域名把所有路径都返回前端页面（SPA catch-all），');
    console.log('        说明真正的 API 地址不在这里，需要到服务商后台查「API 文档/调用说明」。');
  }
}

/* --------------------------------------------- 2. 模型列表 */
console.log('\n[2] 模型列表');
if (!key) {
  console.log('  跳过（未提供密钥）。设置 PROBE_KEY 后重跑即可列出模型 ID。');
} else {
  const r = await probe(`${base}/models`);
  if (r.ok && !r.isHtml && r.status === 200) {
    try {
      const j = JSON.parse(r.raw);
      const ids = (j.data || j.models || []).map((m) => m.id || m.model || m.name).filter(Boolean);
      if (ids.length) {
        console.log(`  共 ${ids.length} 个模型，可直接用作 GENAI_MODEL：`);
        for (const id of ids) console.log('    - ' + id);
      } else {
        console.log('  响应中未找到模型列表字段，原始片段：');
        console.log('    ' + redact(r.raw.slice(0, 400).replace(/\s+/g, ' ')));
      }
    } catch {
      console.log('  响应不是合法 JSON：' + redact(r.raw.slice(0, 200).replace(/\s+/g, ' ')));
    }
  } else {
    console.log('  ' + classify(r) + '（无法列出模型，请到服务商后台查看模型 ID）');
  }
}

/* --------------------------------------------- 3. 可选：最小对话调用 */
if (doChat) {
  console.log('\n[3] 最小 chat 调用（--chat）');
  if (!key) {
    console.log('  跳过（未提供密钥）');
  } else {
    const model = process.env.PROBE_MODEL || '';
    if (!model) {
      console.log('  请设置 PROBE_MODEL 指定模型 ID，例如：');
      console.log('    $env:PROBE_MODEL="deepseek-chat"');
    } else {
      const body = JSON.stringify({
        model,
        messages: [{ role: 'user', content: '只回复两个字：可用' }],
        max_tokens: 16,
        temperature: 0
      });
      const r = await probe(`${base}/chat/completions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body
      });
      console.log('  POST ' + base + '/chat/completions  model=' + model);
      if (r.ok) {
        console.log('      ' + classify(r) + '  [HTTP ' + r.status + ', ' + r.ms + 'ms]');
        console.log('      响应: ' + redact(r.raw.slice(0, 500).replace(/\s+/g, ' ')));
      } else {
        console.log('      连接失败: ' + r.err);
      }
    }
  }
}

console.log('\n' + '='.repeat(74));
console.log(' 下一步：把确认可用的 BASE_URL 与模型 ID 填进 env/.env：');
console.log('   GENAI_BASE_URL=<上面判定为「可用」或「需要鉴权」的那个 base>');
console.log('   GENAI_API_KEY=<你的 key>');
console.log('   GENAI_MODEL=<模型列表里的某个 ID>');
console.log(' 然后运行：node tools/genai-conntest.mjs');
console.log('='.repeat(74));
