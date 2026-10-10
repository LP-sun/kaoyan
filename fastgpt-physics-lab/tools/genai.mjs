#!/usr/bin/env node
/**
 * genai.mjs — 上海科技大学 GenAI API（OpenAI 兼容）最小客户端
 *
 * 安全约定：
 *   - API Key 只从环境变量读取（GENAI_API_KEY），不写入任何文件、不打印到日志。
 *   - 所有错误信息都会对 Key 做脱敏处理后才输出。
 *   - 单次请求默认 max_tokens 很小，避免消耗大量配额。
 *
 * 端点自动探测逻辑（学校网关差异很大，因此不写死）：
 *   1. 若 GENAI_BASE_URL 已以 /chat/completions 结尾，直接使用；
 *   2. 否则依次尝试：
 *        {base}/chat/completions
 *        {base}/v1/chat/completions
 *   3. 第一个返回 2xx 的端点会被缓存，用于后续请求。
 */

import fs from 'node:fs';
import path from 'node:path';

const REDACT_KEYS = ['sk-', 'Bearer '];

/** 把可能含有密钥的字符串脱敏 */
export function redact(text) {
  if (text === undefined || text === null) return '';
  let s = String(text);
  const key = process.env.GENAI_API_KEY;
  if (key && key.length >= 8) {
    s = s.split(key).join('***REDACTED***');
  }
  for (const marker of REDACT_KEYS) {
    s = s.replace(new RegExp(marker.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&') + '[A-Za-z0-9._\\-]{6,}', 'g'), marker + '***REDACTED***');
  }
  return s;
}

/** 极简 .env 读取（不引入任何第三方依赖） */
export function loadEnvFile(file) {
  const out = {};
  if (!fs.existsSync(file)) return out;
  const text = fs.readFileSync(file, 'utf8');
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq <= 0) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    out[key] = value;
  }
  return out;
}

/** 读取配置：优先进程环境变量，其次 env/.env 文件 */
export function loadConfig(rootDir) {
  const envPath = path.join(rootDir, 'env', '.env');
  const fileEnv = loadEnvFile(envPath);
  const pick = (name, fallback = '') => {
    const v = process.env[name];
    if (v !== undefined && v !== '') return v;
    if (fileEnv[name] !== undefined && fileEnv[name] !== '') return fileEnv[name];
    return fallback;
  };
  return {
    envPath,
    envFileExists: fs.existsSync(envPath),
    baseUrl: pick('GENAI_BASE_URL').replace(/\/+$/, ''),
    apiKey: pick('GENAI_API_KEY'),
    model: pick('GENAI_MODEL'),
    modelFallbacks: pick('GENAI_MODEL_FALLBACKS')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
    embeddingModel: pick('GENAI_EMBEDDING_MODEL'),
    diagHost: pick('DIAG_HOST', '127.0.0.1'),
    diagPort: Number(pick('DIAG_PORT', '3101')),
    diagMaxQuestions: Number(pick('DIAG_MAX_QUESTIONS', '10')),
    diagEnableLlm: pick('DIAG_ENABLE_LLM', 'true') === 'true'
  };
}

export function candidateChatUrls(baseUrl) {
  const b = baseUrl.replace(/\/+$/, '');
  if (/\/chat\/completions$/.test(b)) return [b];
  return [`${b}/chat/completions`, `${b}/v1/chat/completions`];
}

export function candidateModelUrls(baseUrl) {
  const b = baseUrl.replace(/\/+$/, '');
  if (/\/models$/.test(b)) return [b];
  return [`${b}/models`, `${b}/v1/models`];
}

export function candidateEmbeddingUrls(baseUrl) {
  const b = baseUrl.replace(/\/+$/, '');
  if (/\/embeddings$/.test(b)) return [b];
  return [`${b}/embeddings`, `${b}/v1/embeddings`];
}

const _resolved = { chat: null, models: null };

async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

/**
 * 探测可用的 chat/completions 端点。
 * @returns {Promise<{ok:boolean, url?:string, status?:number, error?:string, tried:Array}>}
 */
export async function resolveChatUrl(cfg, { timeoutMs = 20000, verbose = false } = {}) {
  if (_resolved.chat) return { ok: true, url: _resolved.chat, tried: [], cached: true };
  const tried = [];
  for (const url of candidateChatUrls(cfg.baseUrl)) {
    try {
      const res = await fetchWithTimeout(
        url,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${cfg.apiKey}`
          },
          body: JSON.stringify({
            model: cfg.model,
            messages: [{ role: 'user', content: 'ping' }],
            max_tokens: 1,
            stream: false
          })
        },
        timeoutMs
      );
      const bodyText = await res.text();
      tried.push({ url, status: res.status });
      if (verbose) console.log(`  [probe] ${url} -> HTTP ${res.status}`);
      // 2xx 说明端点与鉴权都正确
      if (res.ok) {
        _resolved.chat = url;
        return { ok: true, url, status: res.status, tried, body: bodyText };
      }
      // 400/422 也可能是端点正确但参数/模型不被接受，记录但继续尝试
      if (res.status === 401 || res.status === 403) {
        return { ok: false, status: res.status, error: `鉴权失败（HTTP ${res.status}）`, tried, body: bodyText };
      }
    } catch (e) {
      tried.push({ url, error: redact(e.message) });
      if (verbose) console.log(`  [probe] ${url} -> ${redact(e.message)}`);
    }
  }
  return {
    ok: false,
    error: `无法确定可用的 chat/completions 端点，已尝试：${tried.map((t) => t.url + (t.status ? ` (HTTP ${t.status})` : '')).join(' | ')}`,
    tried
  };
}

/**
 * 调用 Chat Completions（非流式）。
 */
export async function chat(cfg, messages, { maxTokens = 512, temperature = 0.2, timeoutMs = 90000, model } = {}) {
  const r = await resolveChatUrl(cfg, { timeoutMs: Math.min(timeoutMs, 20000) });
  if (!r.ok) return { ok: false, error: r.error, tried: r.tried };

  const models = [model || cfg.model, ...cfg.modelFallbacks].filter(Boolean);
  let lastErr = null;

  for (const m of models) {
    try {
      const res = await fetchWithTimeout(
        r.url,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${cfg.apiKey}`
          },
          body: JSON.stringify({
            model: m,
            messages,
            max_tokens: maxTokens,
            temperature,
            stream: false
          })
        },
        timeoutMs
      );
      const text = await res.text();
      if (!res.ok) {
        lastErr = { status: res.status, body: redact(text).slice(0, 400), model: m };
        continue;
      }
      let json;
      try {
        json = JSON.parse(text);
      } catch {
        lastErr = { status: res.status, body: '响应不是合法 JSON: ' + redact(text).slice(0, 200), model: m };
        continue;
      }
      const content =
        json?.choices?.[0]?.message?.content ??
        json?.choices?.[0]?.text ??
        '';
      return {
        ok: true,
        model: m,
        content: typeof content === 'string' ? content : JSON.stringify(content),
        usage: json?.usage || null,
        raw: json
      };
    } catch (e) {
      lastErr = { status: 0, body: redact(e.message), model: m };
    }
  }
  return { ok: false, error: '所有候选模型均调用失败', last: lastErr };
}

/** 可选：列出模型（学校若未开放该接口会返回 404，属正常情况） */
export async function listModels(cfg, { timeoutMs = 20000 } = {}) {
  const tried = [];
  for (const url of candidateModelUrls(cfg.baseUrl)) {
    try {
      const res = await fetchWithTimeout(
        url,
        { method: 'GET', headers: { Authorization: `Bearer ${cfg.apiKey}` } },
        timeoutMs
      );
      const text = await res.text();
      tried.push({ url, status: res.status });
      if (res.ok) {
        let ids = [];
        try {
          const j = JSON.parse(text);
          ids = (j.data || j.models || []).map((m) => m.id || m.name || m.model).filter(Boolean);
        } catch {
          /* ignore */
        }
        return { ok: true, url, status: res.status, ids, tried };
      }
    } catch (e) {
      tried.push({ url, error: redact(e.message) });
    }
  }
  return { ok: false, error: '模型列表接口不可用（学校可能未开放，属正常）', tried };
}

/** 可选：探测 Embedding 接口是否存在 */
export async function probeEmbedding(cfg, { timeoutMs = 20000 } = {}) {
  if (!cfg.embeddingModel) {
    return { ok: false, skipped: true, error: '未配置 GENAI_EMBEDDING_MODEL，跳过' };
  }
  const tried = [];
  for (const url of candidateEmbeddingUrls(cfg.baseUrl)) {
    try {
      const res = await fetchWithTimeout(
        url,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${cfg.apiKey}` },
          body: JSON.stringify({ model: cfg.embeddingModel, input: '测试' })
        },
        timeoutMs
      );
      const text = await res.text();
      tried.push({ url, status: res.status });
      if (res.ok) {
        let dim = null;
        try {
          dim = JSON.parse(text)?.data?.[0]?.embedding?.length ?? null;
        } catch {
          /* ignore */
        }
        return { ok: true, url, status: res.status, dim, tried };
      }
    } catch (e) {
      tried.push({ url, error: redact(e.message) });
    }
  }
  return { ok: false, error: 'Embedding 接口不可用', tried };
}
