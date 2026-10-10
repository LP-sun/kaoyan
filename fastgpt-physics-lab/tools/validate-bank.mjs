#!/usr/bin/env node
/**
 * validate-bank.mjs — 题库结构与一致性校验
 *
 * 检查项：
 *   1. JSON 可解析；题数与 meta.questionCount 一致
 *   2. 每题必备字段齐全
 *   3. 题目 ID 唯一
 *   4. 每题恰有 4 个选项，选项 key 唯一
 *   5. correctOption 必须存在于选项中
 *   6. 每题都有解析
 *   7. chapterMap 中列出的 ID 都真实存在且章节匹配
 *   8. 答案分布不严重偏斜
 *
 * 用法：node tools/validate-bank.mjs [bank/questions.json]
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const BANK = process.argv[2] || path.join(ROOT, 'bank', 'questions.json');

let pass = 0;
let fail = 0;
const problems = [];

function check(name, cond, detail = '') {
  if (cond) {
    pass += 1;
  } else {
    fail += 1;
    problems.push(`${name}${detail ? ' — ' + detail : ''}`);
  }
}

let bank;
try {
  bank = JSON.parse(fs.readFileSync(BANK, 'utf8'));
  check('JSON 可解析', true);
} catch (e) {
  console.error('JSON 解析失败: ' + e.message);
  process.exit(2);
}

const qs = bank.questions || [];
console.log('='.repeat(72));
console.log(' 题库结构校验: ' + BANK);
console.log('='.repeat(72));

check('存在 meta 对象', Boolean(bank.meta));
check('存在 questions 数组', Array.isArray(bank.questions));
check('题数与 meta.questionCount 一致', bank.meta?.questionCount === qs.length, `meta=${bank.meta?.questionCount} 实际=${qs.length}`);
check('题量 = 10（第一版要求）', qs.length === 10, `实际 ${qs.length}`);

/* 每题字段 */
const required = ['id', 'subject', 'chapter', 'knowledgePoints', 'difficulty', 'stem', 'options', 'correctOption', 'explanation'];
const missing = [];
for (const q of qs) {
  for (const f of required) {
    const v = q[f];
    const empty =
      v === undefined ||
      v === null ||
      (typeof v === 'string' && v.trim() === '') ||
      (Array.isArray(v) && v.length === 0);
    if (empty) missing.push(`${q.id || '(无id)'}.${f}`);
  }
  if (!Array.isArray(q.commonMisconceptions) || q.commonMisconceptions.length === 0) {
    missing.push(`${q.id}.commonMisconceptions`);
  }
}
check('所有必备字段齐全', missing.length === 0, missing.join(', '));

/* ID 唯一 */
const ids = qs.map((q) => q.id);
const dupIds = ids.filter((id, i) => ids.indexOf(id) !== i);
check('题目 ID 唯一', dupIds.length === 0, dupIds.join(','));

/* 选项 */
const optProblems = [];
for (const q of qs) {
  if (!Array.isArray(q.options) || q.options.length !== 4) {
    optProblems.push(`${q.id} 选项数=${q.options?.length}`);
    continue;
  }
  const keys = q.options.map((o) => o.key);
  if (new Set(keys).size !== keys.length) optProblems.push(`${q.id} 选项 key 重复`);
  if (!keys.includes(q.correctOption)) optProblems.push(`${q.id} correctOption=${q.correctOption} 不在选项中`);
  if (q.options.some((o) => !o.text || !String(o.text).trim())) optProblems.push(`${q.id} 存在空选项文本`);
}
check('每题 4 个选项且答案可定位', optProblems.length === 0, optProblems.join('; '));

/* 解析质量（粗筛：不能太短） */
const shortExp = qs.filter((q) => typeof q.explanation !== 'string' || q.explanation.length < 30).map((q) => q.id);
check('每题解析不少于 30 字', shortExp.length === 0, shortExp.join(','));

/* chapterMap 一致性 */
const mapProblems = [];
const cm = bank.meta?.chapterMap || {};
for (const [subject, chapters] of Object.entries(cm)) {
  for (const [chapter, idList] of Object.entries(chapters)) {
    for (const id of idList) {
      const q = qs.find((x) => x.id === id);
      if (!q) mapProblems.push(`chapterMap 引用了不存在的 ${id}`);
      else if (q.chapter !== chapter) mapProblems.push(`${id} 章节不匹配（map=${chapter}, 实际=${q.chapter}）`);
      else if (q.subject !== subject) mapProblems.push(`${id} 科目不匹配`);
    }
  }
}
const mappedIds = new Set(Object.values(cm).flatMap((c) => Object.values(c).flat()));
const unmapped = ids.filter((id) => !mappedIds.has(id));
check('chapterMap 引用一致', mapProblems.length === 0, mapProblems.join('; '));
check('所有题目都已纳入 chapterMap', unmapped.length === 0, unmapped.join(','));

/* 答案分布 */
const dist = {};
for (const q of qs) dist[q.correctOption] = (dist[q.correctOption] || 0) + 1;
const maxShare = Math.max(...Object.values(dist)) / qs.length;
check('答案分布不过度偏斜（最高占比 < 60%）', maxShare < 0.6, JSON.stringify(dist));

/* 难度与状态分布 */
const diff = {};
for (const q of qs) diff[q.difficulty] = (diff[q.difficulty] || 0) + 1;
const status = {};
for (const q of qs) status[q.status || '(未标注)'] = (status[q.status || '(未标注)'] || 0) + 1;

console.log('\n统计信息');
console.log('  答案分布 : ' + JSON.stringify(dist));
console.log('  难度分布 : ' + JSON.stringify(diff));
console.log('  状态分布 : ' + JSON.stringify(status));
console.log('  章节分布 : ' + JSON.stringify(
  qs.reduce((acc, q) => { acc[q.chapter] = (acc[q.chapter] || 0) + 1; return acc; }, {})
));

const needReview = qs.filter((q) => q.status !== 'verified').map((q) => q.id);
if (needReview.length) console.log('  待复核题 : ' + needReview.join(', '));

console.log('\n' + '='.repeat(72));
console.log(` 通过 ${pass} 项，失败 ${fail} 项`);
if (problems.length) {
  console.log(' 问题明细：');
  for (const p of problems) console.log('   - ' + p);
}
console.log('='.repeat(72));
process.exitCode = fail === 0 ? 0 : 1;
