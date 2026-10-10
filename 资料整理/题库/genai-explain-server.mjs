import http from 'node:http';
const port = Number(process.env.GENAI_PROXY_PORT || 8787);
const base = (process.env.GENAI_BASE_URL || process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com/v1').replace(/\/$/, '');
const key = process.env.GENAI_API_KEY || process.env.DEEPSEEK_API_KEY;
const model = process.env.GENAI_MODEL || process.env.DEEPSEEK_MODEL || 'deepseek-chat';
const server = http.createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'content-type');
  if (req.method === 'OPTIONS') { res.writeHead(204); return res.end(); }
  if (req.method !== 'POST' || req.url !== '/api/explain') { res.writeHead(404); return res.end('not found'); }
  if (!key) { res.writeHead(500, {'content-type':'application/json'}); return res.end(JSON.stringify({error:'未配置 GENAI_API_KEY'})); }
  let raw=''; for await (const chunk of req) raw += chunk;
  try {
    const body=JSON.parse(raw), prompt=body.prompt || body.question || '';
    const upstream=await fetch(`${base}/chat/completions`, {method:'POST', headers:{'content-type':'application/json', authorization:`Bearer ${key}`}, body:JSON.stringify({model, messages:[{role:'system',content:'你是严谨的考研物理老师。只输出中文讲解，不编造题目条件。'},{role:'user',content:prompt}], temperature:.2, max_tokens:2500})});
    const data=await upstream.json(); if (!upstream.ok) throw Error(data.error?.message || `upstream ${upstream.status}`);
    res.writeHead(200, {'content-type':'application/json; charset=utf-8'}); res.end(JSON.stringify({answer:data.choices?.[0]?.message?.content || ''}));
  } catch (e) { res.writeHead(502, {'content-type':'application/json; charset=utf-8'}); res.end(JSON.stringify({error:e.message})); }
});
server.listen(port, '127.0.0.1', () => console.log(`GenAI proxy listening on http://127.0.0.1:${port}`));
