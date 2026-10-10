#!/usr/bin/env node
/**
 * diagnosis-server.mjs — 物理考研智能诊断（本地独立实现）
 *
 * 这是与 FastGPT 并行的“原生”实现，用于：
 *   1. 在没有 Docker 的环境里立即验证诊断工作流与题库；
 *   2. 作为 FastGPT 工作流的参考实现与对照。
 *
 * 设计要点（与任务要求严格对应）：
 *   - 判分完全使用题库中的固定答案（correctOption），不调用大模型。
 *   - 只有「错因分析」和「学习建议」会调用学校 GenAI API。
 *   - 错因分析只给“可能误区”并标注置信度，绝不把推断写成确定诊断。
 *   - 会话状态独立保存，互不影响；单一会话可随时中止。
 *   - 答案只在下发题目之后、用户提交之后返回，提交前不下发。
 *
 * 运行：node tools/diagnosis-server.mjs
 * 仅监听 127.0.0.1，不对外暴露。
 */

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { loadConfig, chat, resolveChatUrl, redact } from './genai.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const BANK_PATH = path.join(ROOT, 'bank', 'questions.json');
const DATA_DIR = path.join(ROOT, 'data');
const SESSIONS_PATH = path.join(DATA_DIR, 'diagnosis-sessions.json');

const cfg = loadConfig(ROOT);
if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });

const bank = JSON.parse(fs.readFileSync(BANK_PATH, 'utf8'));
const QUESTION_MAP = new Map(bank.questions.map((q) => [q.id, q]));

/* ------------------------------------------------------------------ 会话存储 */

/** @type {Map<string, any>} */
const sessions = new Map();

function persistSessions() {
  try {
    const obj = {};
    for (const [id, s] of sessions) obj[id] = s;
    fs.writeFileSync(SESSIONS_PATH, JSON.stringify(obj, null, 2), 'utf8');
  } catch (e) {
    console.error('[warn] 会话持久化失败:', redact(e.message));
  }
}

function loadSessions() {
  if (!fs.existsSync(SESSIONS_PATH)) return;
  try {
    const obj = JSON.parse(fs.readFileSync(SESSIONS_PATH, 'utf8'));
    for (const [id, s] of Object.entries(obj)) sessions.set(id, s);
    console.log(`[info] 已恢复 ${sessions.size} 个历史会话`);
  } catch (e) {
    console.error('[warn] 会话恢复失败:', redact(e.message));
  }
}

/* ------------------------------------------------------------------ 工具函数 */

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = crypto.randomInt(i + 1);
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/** 对外输出题目时必须剔除答案与解析 */
function publicQuestion(q, index, total) {
  return {
    index,
    total,
    id: q.id,
    subject: q.subject,
    chapter: q.chapter,
    knowledgePoints: q.knowledgePoints,
    difficulty: q.difficulty,
    stem: q.stem,
    options: q.options
  };
}

function buildQueue(subject, chapter, limit) {
  let pool = bank.questions;
  if (subject) pool = pool.filter((q) => q.subject === subject);
  if (chapter) pool = pool.filter((q) => q.chapter === chapter);
  return shuffle(pool).slice(0, limit).map((q) => q.id);
}

function getTaxonomy() {
  const subjects = {};
  for (const q of bank.questions) {
    subjects[q.subject] ??= {};
    subjects[q.subject][q.chapter] ??= 0;
    subjects[q.subject][q.chapter] += 1;
  }
  return { subjects, meta: bank.meta, chapterMap: bank.meta.chapterMap };
}

/* ------------------------------------------------- 错因分析 / 学习建议（LLM） */

const ANALYST_SYSTEM = `你是一位普通物理力学助教，正在分析一名考研学生的选择题作答记录。

严格要求（必须遵守）：
1. 你只能看到学生选择的选项，看不到他的草稿或推理过程。
2. 因此你绝不能断言学生"就是"犯了某个具体错误，只能提出"可能的误区"。
3. 若仅凭一次选错无法区分原因，你必须在 follow_up_question 字段给出一道能区分不同原因的追问。
4. 不要输出解题全过程，只输出诊断信息。
5. 只输出一个 JSON 对象，不要输出 markdown 代码块或任何额外文字。

JSON 结构：
{
  "topic": "知识点名称",
  "correct": true/false,
  "possible_misconceptions": ["可能的误区1", "可能的误区2"],
  "confidence": "low" | "medium" | "high",
  "recommended_review": ["需要复习的具体内容"],
  "follow_up_question": "用于区分上述误区的一道追问（若无必要则填空字符串）"
}`;

function buildAnalysisUserPrompt(q, chosenKey) {
  const chosen = q.options.find((o) => o.key === chosenKey);
  const right = q.options.find((o) => o.key === q.correctOption);
  return `题目（知识点：${q.chapter} / ${q.knowledgePoints.join('、')}，难度：${q.difficulty}）
${q.stem}

选项：
${q.options.map((o) => `${o.key}. ${o.text}`).join('\n')}

学生的作答：${chosenKey}. ${chosen ? chosen.text : '(无效选项)'}
标准答案：${q.correctOption}. ${right ? right.text : ''}

标准解析（供你判断学生可能卡在哪一步，不要复述给学生）：
${q.explanation}

请按系统提示的 JSON 结构输出诊断。`;
}

function extractJson(text) {
  if (!text) return null;
  let t = text.trim();
  // 去掉可能的 ```json 包裹
  t = t.replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
  const start = t.indexOf('{');
  const end = t.lastIndexOf('}');
  if (start === -1 || end === -1 || end <= start) return null;
  try {
    return JSON.parse(t.slice(start, end + 1));
  } catch {
    return null;
  }
}

async function analyzeAnswer(q, chosenKey) {
  if (!cfg.diagEnableLlm) {
    return { ok: false, skipped: true, error: 'DIAG_ENABLE_LLM=false，已跳过模型错因分析' };
  }
  if (!cfg.apiKey || !cfg.model) {
    return { ok: false, error: '未配置 GENAI_API_KEY / GENAI_MODEL，无法进行模型错因分析（判分不受影响）' };
  }
  const res = await chat(
    cfg,
    [
      { role: 'system', content: ANALYST_SYSTEM },
      { role: 'user', content: buildAnalysisUserPrompt(q, chosenKey) }
    ],
    /*
     * maxTokens 必须给足，这是实测踩到的真实坑：
     * 原来这里是 700，用 Kimi-K2.6（不输出思维链）时正常，
     * 但换成 DeepSeek-V4-Flash / GLM-5.3 等模型后，它们会先输出
     * `reasoning_content`（思维链），而**思维链同样计入 completion tokens**。
     * 思维链吃掉配额后正式答案就被截断（finish_reason=length），
     * 表现为"模型返回内容不是可解析的 JSON"——很容易被误判成模型能力不行。
     * 实测：调到 2500 以上，带思维链的模型也能稳定返回完整 JSON。
     */
    { maxTokens: 2500, temperature: 0.2 }
  );
  if (!res.ok) return { ok: false, error: res.error || JSON.stringify(res.last || {}) };
  const parsed = extractJson(res.content);
  if (!parsed) {
    return { ok: false, error: '模型返回内容不是可解析的 JSON', raw: redact(res.content).slice(0, 500) };
  }
  // 兜底规范化，确保不会把推断写成确定结论
  return {
    ok: true,
    model: res.model,
    usage: res.usage,
    analysis: {
      topic: parsed.topic || q.knowledgePoints[0] || q.chapter,
      correct: parsed.correct === true,
      possible_misconceptions: Array.isArray(parsed.possible_misconceptions)
        ? parsed.possible_misconceptions.slice(0, 4)
        : [],
      confidence: ['low', 'medium', 'high'].includes(parsed.confidence) ? parsed.confidence : 'low',
      recommended_review: Array.isArray(parsed.recommended_review) ? parsed.recommended_review.slice(0, 5) : [],
      follow_up_question: typeof parsed.follow_up_question === 'string' ? parsed.follow_up_question : ''
    }
  };
}

const TUTOR_SYSTEM = `你是一位考研物理辅导老师。学生会给你一份本次诊断的作答汇总（每题的知识点、对错、以及基于选择题无法确定的可能误区）。

要求：
1. 只依据给出的汇总，不要假设学生未表现出的问题。
2. 明确指出哪些薄弱环节是"可以确认的"（多次出错/相关知识点连续出错），
   哪些只是"疑似"（仅一次出错，证据不足）。
3. 给出 3 条以内的具体复习建议与一组下一步练习方向。
4. 用简洁中文，分点输出，不超过 350 字。不要输出 JSON。`;

function buildReportSummary(session) {
  const lines = session.records.map((r) => {
    const q = QUESTION_MAP.get(r.questionId);
    return `- 题目ID ${r.questionId}；知识点：${q.chapter} / ${q.knowledgePoints.join('、')}；难度：${q.difficulty}；你的答案：${r.chosenKey}；正确答案：${q.correctOption}；结果：${r.correct ? '正确' : '错误'}`;
  });
  return `本次共作答 ${session.records.length} 题，正确 ${session.records.filter((r) => r.correct).length} 题。\n\n作答明细：\n${lines.join('\n')}`;
}

/** 规则化的诊断报告（不依赖模型，始终可用） */
function ruleBasedReport(session) {
  const byChapter = new Map();
  for (const r of session.records) {
    const q = QUESTION_MAP.get(r.questionId);
    if (!byChapter.has(q.chapter)) byChapter.set(q.chapter, { asked: 0, wrong: 0, wrongIds: [], points: new Set() });
    const c = byChapter.get(q.chapter);
    c.asked += 1;
    q.knowledgePoints.forEach((p) => c.points.add(p));
    if (!r.correct) {
      c.wrong += 1;
      c.wrongIds.push(r.questionId);
    }
  }

  const confirmed = [];
  const suspected = [];
  for (const [chapter, c] of byChapter) {
    if (c.wrong === 0) continue;
    const entry = {
      chapter,
      wrong: c.wrong,
      asked: c.asked,
      wrongIds: c.wrongIds,
      points: [...c.points]
    };
    if (c.wrong >= 2 || (c.asked >= 2 && c.wrong / c.asked >= 0.5)) confirmed.push(entry);
    else suspected.push(entry);
  }

  const allPoints = [];
  for (const c of byChapter.values()) allPoints.push(...c.points);
  const unasked = (bank.meta.chapterMap['力学'] && Object.keys(bank.meta.chapterMap['力学'])) || [];

  const nextPractice = [];
  for (const e of [...confirmed, ...suspected]) {
    const others = bank.questions.filter((q) => q.chapter === e.chapter && !session.records.some((r) => r.questionId === q.id));
    if (others.length) nextPractice.push({ chapter: e.chapter, suggestedQuestionIds: others.map((q) => q.id) });
  }

  return {
    total: session.records.length,
    correctCount: session.records.filter((r) => r.correct).length,
    accuracy: session.records.length ? +(session.records.filter((r) => r.correct).length / session.records.length).toFixed(3) : 0,
    testedPoints: [...new Set(allPoints)],
    testedChapters: [...byChapter.keys()],
    availableChapters: unasked,
    confirmedWeakAreas: confirmed,
    suspectedWeakAreas: suspected,
    nextPractice,
    caveat:
      '本报告只依据选择题的对错统计。选择题的对错不足以证明学生具体犯了哪一类错误，' +
      '「已确认薄弱环节」指相关知识点上出现多次或高比例出错，「疑似」指证据不足，需结合追问或笔算过程进一步确认。'
  };
}

async function llmAdvice(session, ruleReport) {
  if (!cfg.diagEnableLlm) return { ok: false, skipped: true, error: 'DIAG_ENABLE_LLM=false，已跳过模型学习建议' };
  if (!cfg.apiKey || !cfg.model) return { ok: false, error: '未配置 GENAI_API_KEY / GENAI_MODEL' };
  const res = await chat(
    cfg,
    [
      { role: 'system', content: TUTOR_SYSTEM },
      {
        role: 'user',
        content:
          buildReportSummary(session) +
          '\n\n规则统计结果（供参考）：\n' +
          JSON.stringify(
            {
              confirmedWeakAreas: ruleReport.confirmedWeakAreas.map((e) => e.chapter),
              suspectedWeakAreas: ruleReport.suspectedWeakAreas.map((e) => e.chapter)
            },
            null,
            2
          )
      }
    ],
    // 学习建议节点同样要留足配额，理由见上面错因分析节点的说明
    // （带思维链的模型会先消耗 completion tokens，700/800 会被截断）
    { maxTokens: 2500, temperature: 0.3 }
  );
  if (!res.ok) return { ok: false, error: res.error || JSON.stringify(res.last || {}) };
  return { ok: true, model: res.model, usage: res.usage, advice: res.content.trim() };
}

/* ------------------------------------------------------------------ HTTP 层 */

function json(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store'
  });
  res.end(body);
}

async function readBody(req) {
  const chunks = [];
  let size = 0;
  for await (const c of req) {
    size += c.length;
    if (size > 1_000_000) throw new Error('请求体过大');
    chunks.push(c);
  }
  if (!chunks.length) return {};
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    throw new Error('请求体不是合法 JSON');
  }
}

function currentQuestion(session) {
  if (session.finished) return null;
  const id = session.queue[session.cursor];
  if (!id) return null;
  const q = QUESTION_MAP.get(id);
  return publicQuestion(q, session.cursor + 1, session.queue.length);
}

const routes = {
  'GET /api/health': async (req, res) => {
    json(res, 200, {
      ok: true,
      service: 'fastgpt-physics-lab / 物理考研智能诊断（本地实现）',
      bankQuestions: bank.questions.length,
      llmEnabled: cfg.diagEnableLlm,
      genaiConfigured: Boolean(cfg.apiKey && cfg.model && cfg.baseUrl),
      activeSessions: sessions.size
    });
  },

  'GET /api/taxonomy': async (req, res) => {
    json(res, 200, getTaxonomy());
  },

  'POST /api/session': async (req, res) => {
    const body = await readBody(req);
    const subject = body.subject || '力学';
    const chapter = body.chapter || null;
    const limit = Math.max(1, Math.min(Number(body.limit) || cfg.diagMaxQuestions, bank.questions.length));
    const queue = buildQueue(subject, chapter, limit);
    if (queue.length === 0) return json(res, 400, { error: '该科目/章节下没有题目' });
    const id = crypto.randomUUID();
    const session = {
      id,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      subject,
      chapter,
      queue,
      cursor: 0,
      records: [],
      finished: false
    };
    sessions.set(id, session);
    persistSessions();
    json(res, 201, { sessionId: id, question: currentQuestion(session), total: queue.length });
  },

  'GET /api/session': async (req, res, url) => {
    const id = url.searchParams.get('id');
    const s = sessions.get(id);
    if (!s) return json(res, 404, { error: '会话不存在或已过期' });
    json(res, 200, {
      sessionId: s.id,
      subject: s.subject,
      chapter: s.chapter,
      cursor: s.cursor,
      total: s.queue.length,
      answered: s.records.length,
      finished: s.finished,
      question: currentQuestion(s)
    });
  },

  'POST /api/answer': async (req, res) => {
    const body = await readBody(req);
    const s = sessions.get(body.sessionId);
    if (!s) return json(res, 404, { error: '会话不存在或已过期' });
    if (s.finished) return json(res, 409, { error: '本次诊断已结束，请开始新的诊断' });

    const qid = s.queue[s.cursor];
    if (!qid) return json(res, 409, { error: '没有待作答的题目' });
    if (body.questionId && body.questionId !== qid) {
      return json(res, 409, { error: `题目不匹配：当前应作答 ${qid}` });
    }
    const q = QUESTION_MAP.get(qid);

    const chosenKey = String(body.choice || '').trim().toUpperCase();
    if (!q.options.some((o) => o.key === chosenKey)) {
      return json(res, 400, { error: '无效选项' });
    }

    // 固定答案判分：不调用任何模型
    const correct = chosenKey === q.correctOption;

    // 模型错因分析（仅错误题，且失败不影响判分）
    let analysis = null;
    let analysisError = null;
    if (!correct) {
      const a = await analyzeAnswer(q, chosenKey);
      if (a.ok) analysis = a.analysis;
      else analysisError = a.error;
    }

    const record = {
      questionId: qid,
      chosenKey,
      correct,
      answeredAt: new Date().toISOString(),
      analysis
    };
    s.records.push(record);
    s.cursor += 1;
    s.updatedAt = new Date().toISOString();
    if (s.cursor >= s.queue.length) s.finished = true;
    persistSessions();

    json(res, 200, {
      questionId: qid,
      chosenKey,
      correct,
      correctOption: q.correctOption,
      explanation: q.explanation,
      commonMisconceptions: q.commonMisconceptions,
      analysis,
      analysisError,
      finished: s.finished,
      nextQuestion: currentQuestion(s),
      progress: { answered: s.records.length, total: s.queue.length }
    });
  },

  'POST /api/report': async (req, res) => {
    const body = await readBody(req);
    const s = sessions.get(body.sessionId);
    if (!s) return json(res, 404, { error: '会话不存在或已过期' });
    if (s.records.length === 0) return json(res, 409, { error: '尚无作答记录，无法生成报告' });

    const rule = ruleBasedReport(s);
    const advice = await llmAdvice(s, rule);
    json(res, 200, {
      sessionId: s.id,
      finished: s.finished,
      ruleReport: rule,
      llmAdvice: advice.ok ? { advice: advice.advice, model: advice.model, usage: advice.usage } : null,
      llmAdviceError: advice.ok ? null : advice.error,
      detail: s.records.map((r) => ({
        questionId: r.questionId,
        chapter: QUESTION_MAP.get(r.questionId).chapter,
        chosenKey: r.chosenKey,
        correctKey: QUESTION_MAP.get(r.questionId).correctOption,
        correct: r.correct
      })),
      disclaimer:
        '错因与薄弱环节属于基于答题表现的推断，不是确定诊断结论。' +
        '本次记录只保存在本机 data/diagnosis-sessions.json，未写入 PhysicsPrep 的任何数据库。'
    });
  },

  'POST /api/session/stop': async (req, res) => {
    const body = await readBody(req);
    const s = sessions.get(body.sessionId);
    if (!s) return json(res, 404, { error: '会话不存在或已过期' });
    s.finished = true;
    s.stoppedAt = new Date().toISOString();
    s.updatedAt = s.stoppedAt;
    persistSessions();
    json(res, 200, { ok: true, finished: true, answered: s.records.length });
  },

  'GET /api/genai/status': async (req, res) => {
    const probe = await resolveChatUrl(cfg);
    json(res, 200, {
      baseUrlConfigured: Boolean(cfg.baseUrl),
      modelConfigured: Boolean(cfg.model),
      apiKeyConfigured: Boolean(cfg.apiKey),
      chatEndpointResolved: probe.ok ? probe.url : null,
      probeError: probe.ok ? null : probe.error,
      note: '本接口不会回显任何密钥内容。'
    });
  },

  'POST /api/genai/test': async (req, res) => {
    if (!cfg.apiKey || !cfg.model || !cfg.baseUrl) {
      return json(res, 400, {
        ok: false,
        error: '尚未配置 GENAI_BASE_URL / GENAI_API_KEY / GENAI_MODEL，请编辑 env/.env 后重启本服务'
      });
    }
    const t0 = Date.now();
    const r = await chat(
      cfg,
      [
        { role: 'system', content: '你是一个测试助手，请严格按用户要求回答。' },
        { role: 'user', content: '请用中文回答：1+1 等于几？只回答数字。' }
      ],
      /*
       * 探活请求：故意用很小的配额，避免为了"测通不通"而消耗大量额度。
       * 但也不能太小：带思维链的模型（DeepSeek-V4-Flash 等）会先输出
       * reasoning_content 且同样计入配额，曾用 24 时可能把配额吃光、
       * 导致连通性探测误报"失败"（其实是模型在思考）。600 足够且仍很便宜。
       */
      { maxTokens: 600, temperature: 0 }
    );
    json(res, 200, {
      ok: r.ok,
      latencyMs: Date.now() - t0,
      model: r.model || null,
      answer: r.ok ? r.content.trim() : null,
      usage: r.usage || null,
      error: r.ok ? null : r.error || JSON.stringify(r.last || {})
    });
  }
};

function serveIndex(res) {
  const indexPath = path.join(ROOT, 'tools', 'index.html');
  if (!fs.existsSync(indexPath)) {
    res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
    return res.end('index.html 缺失');
  }
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(fs.readFileSync(indexPath, 'utf8'));
}

/* 本地静态资源：仅暴露 /vendor/katex/*，映射到 third_party/katex/dist */
const KATEX_DIST = path.join(ROOT, 'third_party', 'katex', 'dist');
const MIME = {
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.ttf': 'font/ttf',
  '.json': 'application/json; charset=utf-8'
};

function serveVendor(res, urlPath) {
  const rel = urlPath.replace(/^\/vendor\/katex\//, '');
  if (rel.includes('..') || rel.includes('\\') || rel.startsWith('/')) {
    res.writeHead(400).end('bad path');
    return;
  }
  const abs = path.join(KATEX_DIST, rel);
  if (!abs.startsWith(KATEX_DIST) || !fs.existsSync(abs) || !fs.statSync(abs).isFile()) {
    res.writeHead(404).end('not found');
    return;
  }
  res.writeHead(200, {
    'Content-Type': MIME[path.extname(abs).toLowerCase()] || 'application/octet-stream',
    'Cache-Control': 'public, max-age=86400'
  });
  res.end(fs.readFileSync(abs));
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || '127.0.0.1'}`);
  const key = `${req.method} ${url.pathname}`;
  try {
    if (req.method === 'GET' && (url.pathname === '/' || url.pathname === '/index.html')) {
      return serveIndex(res);
    }
    if (req.method === 'GET' && url.pathname.startsWith('/vendor/katex/')) {
      return serveVendor(res, url.pathname);
    }
    const handler = routes[key];
    if (!handler) return json(res, 404, { error: `未知接口 ${key}` });
    await handler(req, res, url);
  } catch (e) {
    console.error('[error]', redact(e.stack || e.message));
    if (!res.headersSent) json(res, 500, { error: redact(e.message) });
  }
});

loadSessions();

server.listen(cfg.diagPort, cfg.diagHost, () => {
  console.log('==============================================================');
  console.log(' 物理考研智能诊断（本地独立实现，非 FastGPT）');
  console.log('--------------------------------------------------------------');
  console.log(` 访问地址 : http://${cfg.diagHost}:${cfg.diagPort}`);
  console.log(` 题库     : ${bank.questions.length} 题（${BANK_PATH}）`);
  console.log(` 配置文件 : ${cfg.envPath} (${cfg.envFileExists ? '已存在' : '不存在，请从 .env.example 复制'})`);
  console.log(` GenAI    : ${cfg.apiKey && cfg.model && cfg.baseUrl ? '参数已配置' : '参数未配置（判分仍可用，错因分析将不可用）'}`);
  console.log(` 模型分析 : ${cfg.diagEnableLlm ? '已启用' : '已禁用'}`);
  console.log(` 数据文件 : ${SESSIONS_PATH}`);
  console.log('==============================================================');
});
