#!/usr/bin/env node
/**
 * mock-openai.mjs — 本地模拟的 OpenAI 兼容服务端（仅用于自测接入管道）
 *
 * 目的：在没有学校真实密钥的情况下，验证 tools/genai.mjs 的
 *       端点探测、鉴权、中文回答、JSON 指令遵循、错误处理等逻辑是否正确。
 *
 * 有意设计的"不友好"行为，用于检验探测逻辑：
 *   - 只暴露 /v1/chat/completions，不暴露 /chat/completions
 *     （真实网关常见差异，用于验证回退探测）
 *   - 鉴权头错误时返回 401
 *   - 未知模型名返回 400
 *
 * 仅监听 127.0.0.1:3199。绝不用于生产，也不代理任何真实流量。
 *
 * 用法：node tools/mock-openai.mjs
 */

import http from 'node:http';

const PORT = 3199;
const HOST = '127.0.0.1';
const VALID_KEY = 'mock-key-for-pipeline-test';
const VALID_MODELS = ['mock-model-a', 'mock-model-b'];

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${HOST}:${PORT}`);

  const send = (code, obj) => {
    res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify(obj));
  };

  // 收集请求体
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const raw = Buffer.concat(chunks).toString('utf8');
  let body = {};
  try {
    body = raw ? JSON.parse(raw) : {};
  } catch {
    return send(400, { error: { message: 'invalid JSON body', type: 'invalid_request_error' } });
  }

  const auth = req.headers.authorization || '';
  const token = auth.replace(/^Bearer\s+/i, '');
  if (token !== VALID_KEY) {
    return send(401, { error: { message: 'invalid api key', type: 'authentication_error' } });
  }

  // 只支持 /v1/models 与 /v1/chat/completions；/models 故意返回 404
  if (url.pathname === '/v1/models' && req.method === 'GET') {
    return send(200, { object: 'list', data: VALID_MODELS.map((id) => ({ id, object: 'model' })) });
  }

  if (url.pathname === '/chat/completions') {
    return send(404, { error: { message: 'not found: use /v1/chat/completions', type: 'invalid_request_error' } });
  }

  if (url.pathname === '/v1/chat/completions' && req.method === 'POST') {
    const model = body.model;
    if (!VALID_MODELS.includes(model)) {
      return send(400, { error: { message: `model ${model} not found`, type: 'invalid_request_error' } });
    }
    const lastUser = [...(body.messages || [])].reverse().find((m) => m.role === 'user');
    const prompt = lastUser?.content || '';
    const systemMsg = (body.messages || []).find((m) => m.role === 'system')?.content || '';
    let content = '好的。';
    if (prompt.includes('首都')) content = '北京';
    else if (prompt.includes('1+1')) content = '2';
    else if (prompt.includes('{"ok":true}')) content = '{"ok":true}';
    else if (prompt.startsWith('ping')) content = 'pong';
    else if (systemMsg.includes('JSON 结构') && systemMsg.includes('possible_misconceptions')) {
      // 模拟「错因分析」节点的结构化输出
      content = JSON.stringify({
        topic: '刚体转动',
        correct: false,
        possible_misconceptions: [
          '转动方程与平动方程混淆（把 M=Jβ 写成 M=J/β）',
          '漏加平行轴定理中的 md² 项'
        ],
        confidence: 'low',
        recommended_review: ['合外力矩与角加速度的关系', '平行轴定理的适用条件'],
        follow_up_question: '请写出匀质细棒绕一端垂直轴的转动惯量表达式，并说明推导时用到了哪条定理。'
      });
    } else if (systemMsg.includes('考研物理辅导老师')) {
      // 模拟「学习建议」节点的自然语言输出
      content =
        '1. 可以确认的薄弱环节：刚体转动，相关题连续出错。\n' +
        '2. 疑似薄弱环节：纯滚动中的静摩擦方向，仅一题出错，证据不足。\n' +
        '3. 建议：先复习转动定律与平行轴定理，再练纯滚动能量分配；下一组练习建议覆盖刚体转动与纯滚动各 2 题。';
    }

    const promptTokens = Math.ceil(prompt.length / 3);
    return send(200, {
      id: 'chatcmpl-mock',
      object: 'chat.completion',
      model,
      choices: [{ index: 0, message: { role: 'assistant', content }, finish_reason: 'stop' }],
      usage: {
        prompt_tokens: promptTokens,
        completion_tokens: Math.ceil(content.length / 2),
        total_tokens: promptTokens + Math.ceil(content.length / 2)
      }
    });
  }

  send(404, { error: { message: `unknown route ${req.method} ${url.pathname}`, type: 'invalid_request_error' } });
});

server.listen(PORT, HOST, () => {
  console.log(`[mock-openai] listening on http://${HOST}:${PORT}`);
  console.log(`[mock-openai] valid key : ${VALID_KEY}`);
  console.log(`[mock-openai] valid models: ${VALID_MODELS.join(', ')}`);
  console.log('[mock-openai] 仅用于自测，接口地址请使用 http://127.0.0.1:3199/v1');
});
