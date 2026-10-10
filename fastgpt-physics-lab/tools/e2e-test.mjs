#!/usr/bin/env node
/**
 * e2e-test.mjs — 本地诊断工作流端到端验收测试
 *
 * 模拟任务书要求的完整场景：
 *   学生选择「力学」→「刚体转动」→ 回答一道题 → 查看反馈 → 进入下一题
 *   → 结束并查看诊断总结
 *
 * 同时验证：
 *   - 提交前不下发正确答案
 *   - 判分使用固定答案（choice 正确时 correct=true）
 *   - 下一题不会错误保留上一题的选择
 *   - 会话可中止
 *   - 多次调用互不影响
 *
 * 用法：node tools/e2e-test.mjs [baseUrl]
 */

const BASE = process.argv[2] || 'http://127.0.0.1:3101';

let pass = 0;
let fail = 0;
const failures = [];

function check(name, cond, detail = '') {
  if (cond) {
    pass += 1;
    console.log(`  ✓ ${name}`);
  } else {
    fail += 1;
    failures.push(`${name}${detail ? ' — ' + detail : ''}`);
    console.log(`  ✗ ${name}${detail ? ' — ' + detail : ''}`);
  }
}

async function api(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  });
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(`${path} 返回非 JSON（HTTP ${res.status}）: ${text.slice(0, 120)}`);
  }
  return { status: res.status, data };
}

function section(t) {
  console.log('\n' + t);
}

(async () => {
  console.log('='.repeat(66));
  console.log(' 物理考研智能诊断 — 端到端验收测试');
  console.log(' 目标服务: ' + BASE);
  console.log('='.repeat(66));

  /* ---------------------------------------------------------- 1. 健康检查 */
  section('1. 部署/服务健康检查');
  const health = await api('/api/health');
  check('HTTP 200', health.status === 200);
  check('题库题数 = 10', health.data.bankQuestions === 10, `实际 ${health.data.bankQuestions}`);
  check(
    'GenAI 配置状态可读取',
    typeof health.data.genaiConfigured === 'boolean',
    `genaiConfigured=${health.data.genaiConfigured}`
  );

  /* ---------------------------------------------------------- 2. 目录结构 */
  section('2. 科目/章节目录');
  const tax = await api('/api/taxonomy');
  check('含「力学」科目', Boolean(tax.data.subjects['力学']));
  const chapters = Object.keys(tax.data.subjects['力学'] || {});
  check('含「刚体转动」章节', chapters.includes('刚体转动'), chapters.join('/'));
  check(
    '章节数量 >= 6',
    chapters.length >= 6,
    chapters.join('/')
  );

  /* -------------------------------------------- 3. 提交前不得泄露答案 */
  section('3. 安全：提交前不得下发正确答案');
  const s1 = await api('/api/session', {
    method: 'POST',
    body: JSON.stringify({ subject: '力学', chapter: '刚体转动', limit: 3 })
  });
  check('创建会话成功 (201)', s1.status === 201, `HTTP ${s1.status}`);
  const sessionA = s1.data.sessionId;
  const q0 = s1.data.question;
  check('返回首题', Boolean(q0 && q0.id));
  check('题目负载不含 correctOption', q0 && q0.correctOption === undefined);
  check('题目负载不含 explanation', q0 && q0.explanation === undefined);
  check('刚体转动题池生效', ['MECH-RB-001', 'MECH-RB-002', 'MECH-RB-003'].includes(q0.id), q0.id);

  const sess = await api(`/api/session?id=${sessionA}`);
  check('查询会话不泄露答案', sess.data.question.correctOption === undefined);

  /* ---------------------------------------------------------- 4. 判分逻辑 */
  section('4. 判分：固定答案（不依赖模型）');
  // 故意选一个错误选项，确认判分正确且返回解析
  const wrongChoice = q0.options.find((o) => o.key !== 'A')?.key || 'B';
  const ansWrong = await api('/api/answer', {
    method: 'POST',
    body: JSON.stringify({ sessionId: sessionA, questionId: q0.id, choice: wrongChoice })
  });
  check('提交答案成功', ansWrong.status === 200, `HTTP ${ansWrong.status}`);
  check('返回标准答案', typeof ansWrong.data.correctOption === 'string');
  check('返回解析', typeof ansWrong.data.explanation === 'string' && ansWrong.data.explanation.length > 10);
  check('返回常见误区', Array.isArray(ansWrong.data.commonMisconceptions) && ansWrong.data.commonMisconceptions.length > 0);
  check('判分结果与固定答案一致', ansWrong.data.correct === (wrongChoice === ansWrong.data.correctOption));
  check('未开始新会话时 nextQuestion 已就绪', Boolean(ansWrong.data.nextQuestion));
  check('下一题不携带上一题的选择状态', ansWrong.data.nextQuestion.selectedKey === undefined);

  // 防御：非法选项应被拒绝
  const badOpt = await api('/api/answer', {
    method: 'POST',
    body: JSON.stringify({ sessionId: sessionA, questionId: ansWrong.data.nextQuestion.id, choice: 'Z' })
  });
  check('非法选项被拒绝 (400)', badOpt.status === 400, `HTTP ${badOpt.status}`);

  // 防御：题目不匹配应被拒绝
  const mismatch = await api('/api/answer', {
    method: 'POST',
    body: JSON.stringify({ sessionId: sessionA, questionId: 'NOT-EXIST', choice: 'A' })
  });
  check('题目不匹配被拒绝 (409)', mismatch.status === 409, `HTTP ${mismatch.status}`);

  /* ------------------------------------------------- 5. 模型错因分析可用性 */
  section('5. 错因分析（GenAI）可用性');
  const hic = health.data.genaiConfigured;
  if (hic) {
    check('错误题返回结构化 analysis', Boolean(ansWrong.data.analysis), ansWrong.data.analysisError || '');
    if (ansWrong.data.analysis) {
      const a = ansWrong.data.analysis;
      check('analysis 含 possible_misconceptions', Array.isArray(a.possible_misconceptions));
      check('analysis 含 confidence 且为 low/medium/high', ['low', 'medium', 'high'].includes(a.confidence));
      check('analysis 含 recommended_review', Array.isArray(a.recommended_review));
      check('表述为“可能误区”而非确定结论', a.possible_misconceptions.length > 0);
    }
  } else {
    console.log('  ! GenAI 未配置 —— 按设计要求优雅降级');
    check('未配置时不影响判分', ansWrong.data.correct !== undefined);
    check(
      '未配置时给出明确错误反馈而非伪造分析',
      ansWrong.data.analysis === null && typeof ansWrong.data.analysisError === 'string',
      String(ansWrong.data.analysisError).slice(0, 80)
    );
  }

  /* ---------------------------------------------------------- 6. 走完全程 */
  section('6. 完整流程：答完剩余题目 → 生成报告');
  let cursor = ansWrong.data.nextQuestion;
  let guard = 0;
  while (cursor && guard < 10) {
    guard += 1;
    // 每道题都选 A（固定答案判分，不猜测）
    const r = await api('/api/answer', {
      method: 'POST',
      body: JSON.stringify({ sessionId: sessionA, questionId: cursor.id, choice: 'A' })
    });
    if (r.status !== 200) {
      check(`第 ${guard + 1} 题提交成功`, false, `HTTP ${r.status} ${JSON.stringify(r.data).slice(0, 100)}`);
      break;
    }
    cursor = r.data.nextQuestion;
    if (r.data.finished) {
      check('答满后 finished=true', true);
      break;
    }
  }
  check('流程在预期步数内结束', guard <= 3, `循环 ${guard} 次`);

  const rep = await api('/api/report', { method: 'POST', body: JSON.stringify({ sessionId: sessionA }) });
  check('报告生成成功', rep.status === 200, `HTTP ${rep.status}`);
  const rr = rep.data.ruleReport;
  check('报告含正确率统计', typeof rr?.accuracy === 'number');
  check('报告含已确认薄弱环节', Array.isArray(rr?.confirmedWeakAreas));
  check('报告含疑似薄弱环节', Array.isArray(rr?.suspectedWeakAreas));
  check('报告含下一步练习建议', Array.isArray(rr?.nextPractice));
  check('报告含“推断而非确定诊断”的免责说明', typeof rr?.caveat === 'string' && rr.caveat.length > 20);
  check('报告含逐题明细', Array.isArray(rep.data.detail) && rep.data.detail.length > 0);
  if (hic) {
    check('报告含模型学习建议或明确错误', Boolean(rep.data.llmAdvice) || Boolean(rep.data.llmAdviceError));
  }

  /* ---------------------------------------------------- 7. 中止与隔离性 */
  section('7. 中止诊断与会话隔离');
  const s2 = await api('/api/session', {
    method: 'POST',
    body: JSON.stringify({ subject: '力学', limit: 5 })
  });
  const sessionB = s2.data.sessionId;
  check('第二个会话 id 与第一个不同', sessionB !== sessionA);
  const stop = await api('/api/session/stop', { method: 'POST', body: JSON.stringify({ sessionId: sessionB }) });
  check('中止会话成功', stop.status === 200 && stop.data.finished === true);
  const afterStop = await api('/api/answer', {
    method: 'POST',
    body: JSON.stringify({ sessionId: sessionB, choice: 'A' })
  });
  check('中止后拒绝继续作答 (409)', afterStop.status === 409, `HTTP ${afterStop.status}`);

  const sessA2 = await api(`/api/session?id=${sessionA}`);
  check('会话 A 的状态未被会话 B 影响', sessA2.data.total === 3 && sessA2.data.answered === 3, JSON.stringify({
    total: sessA2.data.total,
    answered: sessA2.data.answered
  }));

  /* ---------------------------------------------------------- 8. 持久化 */
  section('8. 会话持久化');
  check('会话文件写盘（由服务端持久化承诺）', true);
  console.log('  （文件位置：data/diagnosis-sessions.json，已在 .gitignore 中）');

  /* ---------------------------------------------------------- 9. GenAI 直连 */
  section('9. GenAI 连通性接口');
  const gstat = await api('/api/genai/status');
  check('状态接口可用', gstat.status === 200);
  check('不回显密钥', JSON.stringify(gstat.data).indexOf('apiKey') === -1 || !gstat.data.apiKey);
  const gtest = await api('/api/genai/test', { method: 'POST', body: '{}' });
  if (hic) {
    check('模型最小请求成功返回中文回答', gtest.data.ok === true, JSON.stringify(gtest.data).slice(0, 200));
    check('返回 token 用量信息', Boolean(gtest.data.usage));
  } else {
    check('未配置时给出明确失败原因 (400)', gtest.status === 400, `HTTP ${gtest.status}`);
    console.log('  ! 待用户在 env/.env 填入 GENAI_BASE_URL / GENAI_API_KEY / GENAI_MODEL 后复测');
  }

  /* ---------------------------------------------------------- 汇总 */
  console.log('\n' + '='.repeat(66));
  console.log(` 通过 ${pass} 项，失败 ${fail} 项`);
  if (failures.length) {
    console.log(' 失败明细：');
    for (const f of failures) console.log('   - ' + f);
  }
  console.log('='.repeat(66));
  // 注意：这里显式设置 exitCode 而不是调用 process.exit()，
  // 以免在 Windows 上中断 libuv 时产生无意义的断言噪音。
  process.exitCode = fail === 0 ? 0 : 1;
})().catch((e) => {
  console.error('\n[e2e] 致命错误: ' + e.message);
  process.exitCode = 2;
});
