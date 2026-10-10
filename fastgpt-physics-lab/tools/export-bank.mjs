#!/usr/bin/env node
/**
 * export-bank.mjs — 把 bank/questions.json 导出为便于阅读与录入的格式
 *
 * 用途：
 *   - 生成给人看的 Markdown（含答案与解析，答案与题目分开，避免误看）
 *   - 生成 CSV，便于导入表格或逐条录入 FastGPT 工作流
 *   - 生成 FastGPT「题库常量」片段（bank/bank.const.js），供工作流 code 节点使用
 *
 * 用法：
 *   node tools/export-bank.mjs            # 生成全部三种
 *   node tools/export-bank.mjs --md
 *   node tools/export-bank.mjs --csv
 *   node tools/export-bank.mjs --const
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const BANK = path.join(ROOT, 'bank', 'questions.json');
const bank = JSON.parse(fs.readFileSync(BANK, 'utf8'));

const args = process.argv.slice(2);
const wantAll = args.length === 0;
const want = (f) => wantAll || args.includes(f);

/* ------------------------------------------------------------------ Markdown */
function toMarkdown() {
  const L = [];
  L.push(`# ${bank.meta.title}`);
  L.push('');
  L.push(`- 应用名称：${bank.meta.appName} / ${bank.meta.displayName}`);
  L.push(`- 范围：${bank.meta.scope}`);
  L.push(`- 题量：${bank.questions.length} 题`);
  L.push(`- 来源：${bank.meta.origin}`);
  L.push(`- 判分：${bank.meta.grading}`);
  L.push(`- 说明：${bank.meta.disclaimer}`);
  L.push('');
  L.push('> 本文件由 `tools/export-bank.mjs` 自动生成，请勿手工修改；');
  L.push('> 要改题目请编辑 `bank/questions.json` 后重新生成。');
  L.push('');
  L.push('---');
  L.push('');

  // 按章节分组
  const byChapter = new Map();
  for (const q of bank.questions) {
    if (!byChapter.has(q.chapter)) byChapter.set(q.chapter, []);
    byChapter.get(q.chapter).push(q);
  }
  for (const [chapter, list] of byChapter) {
    L.push(`## ${chapter}`);
    L.push('');
    for (const q of list) {
      L.push(`### ${q.id}（${q.difficulty}）`);
      L.push('');
      L.push(`知识点：${q.knowledgePoints.join('、')}`);
      L.push('');
      L.push(q.stem);
      L.push('');
      for (const o of q.options) L.push(`${o.key}. ${o.text}`);
      L.push('');
    }
  }

  L.push('---');
  L.push('');
  L.push('# 答案与解析（不提前展示给学生）');
  L.push('');
  for (const q of bank.questions) {
    L.push(`## ${q.id}`);
    L.push('');
    L.push(`- 正确答案：**${q.correctOption}**`);
    L.push(`- 状态：${q.status}`);
    L.push('');
    L.push(`**解析**：${q.explanation}`);
    L.push('');
    L.push('**常见误区**：');
    for (const m of q.commonMisconceptions) L.push(`- ${m}`);
    L.push('');
  }
  return L.join('\n');
}

/* ----------------------------------------------------------------------- CSV */
function csvEscape(v) {
  const s = String(v ?? '');
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

function toCsv() {
  const header = [
    'id', 'subject', 'chapter', 'knowledgePoints', 'difficulty',
    'stem', 'A', 'B', 'C', 'D', 'correctOption', 'explanation', 'commonMisconceptions', 'status'
  ];
  const rows = [header.join(',')];
  for (const q of bank.questions) {
    const opt = (k) => q.options.find((o) => o.key === k)?.text ?? '';
    rows.push([
      q.id, q.subject, q.chapter, q.knowledgePoints.join('|'), q.difficulty,
      q.stem, opt('A'), opt('B'), opt('C'), opt('D'),
      q.correctOption, q.explanation, q.commonMisconceptions.join('|'), q.status
    ].map(csvEscape).join(','));
  }
  // 加 BOM，避免 Excel 打开中文乱码
  return '\uFEFF' + rows.join('\r\n');
}

/* -------------------------------------------------- FastGPT code 节点常量片段 */
function toConst() {
  const slim = bank.questions.map((q) => ({
    id: q.id,
    subject: q.subject,
    chapter: q.chapter,
    knowledgePoints: q.knowledgePoints,
    difficulty: q.difficulty,
    stem: q.stem,
    options: q.options,
    correctOption: q.correctOption,
    explanation: q.explanation,
    commonMisconceptions: q.commonMisconceptions
  }));
  return `/**
 * bank.const.js — 题库常量（自动生成，请勿手工修改）
 * 生成命令：node tools/export-bank.mjs --const
 * 用途：粘贴到 FastGPT 工作流 [C] code 节点中作为题库来源（不依赖向量库与 Embedding）。
 */
const QUESTION_BANK = ${JSON.stringify(slim, null, 2)};

/** 按科目与章节取题；chapter 传 "ALL" 或空表示不限章节 */
function pickQuestions(chapter, limit) {
  const pool = !chapter || chapter === 'ALL'
    ? QUESTION_BANK
    : QUESTION_BANK.filter((q) => q.chapter === chapter);
  return pool.slice(0, limit || pool.length);
}

/** 对外输出题目时必须剔除答案与解析，避免提前泄露 */
function publicView(q, index, total) {
  return {
    index: index + 1,
    total,
    id: q.id,
    stem: q.stem,
    options: q.options
  };
}

module.exports = { QUESTION_BANK, pickQuestions, publicView };
`;
}

/* ---------------------------------------------------------------------- 输出 */
const outDir = path.join(ROOT, 'bank');
const written = [];

if (want('--md')) {
  const p = path.join(outDir, 'questions.md');
  fs.writeFileSync(p, toMarkdown(), 'utf8');
  written.push(p);
}
if (want('--csv')) {
  const p = path.join(outDir, 'questions.csv');
  fs.writeFileSync(p, toCsv(), 'utf8');
  written.push(p);
}
if (want('--const')) {
  const p = path.join(outDir, 'bank.const.js');
  fs.writeFileSync(p, toConst(), 'utf8');
  written.push(p);
}

console.log('已生成：');
for (const p of written) {
  console.log(`  - ${p}  (${fs.statSync(p).size} bytes)`);
}
console.log('\n提示：bank/questions.csv 与 bank/questions.md 属于派生文件，');
console.log('      真正的题源是 bank/questions.json；改动请改题库后重新生成。');
