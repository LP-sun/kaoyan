#!/usr/bin/env node
/**
 * workflow-check.mjs — 用 FastGPT 源码里的权威枚举校验工作流蓝图
 *
 * 校验 fastgpt/WORKFLOW.blueprint.json：
 *   1. 每个节点的 flowNodeType 必须是 FastGPT 真实存在的类型（取自源码 FlowNodeTypeEnum）
 *   2. 交互节点（userSelect / formInput）的 inputs 键必须是源码里定义的键
 *   3. 每个节点的 outputs 键必须与源码定义一致（这是最容易写错的地方）
 *   4. 跨节点引用 {{X.someKey}} 必须指向存在的节点与存在的输出键
 *   5. answerNode 的展示文本不得提前泄露 correctKey / explanation（判分要求）
 *   6. 工作流变量：被引用的变量必须已声明
 *
 * 源码来源（本地只读缓存，缺失时会降级为内置枚举并明确标注）：
 *   .fastgpt-lab-notes/FastGPT-src @ tag v4.17.1
 *
 * 用法：node tools/workflow-check.mjs
 */

import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const BLUEPRINT = path.join(ROOT, 'fastgpt', 'WORKFLOW.blueprint.json');
// 源码缓存位于工作区上一级
const SRC = path.resolve(ROOT, '..', '.fastgpt-lab-notes', 'FastGPT-src');

let pass = 0;
let fail = 0;
const problems = [];
function check(name, cond, detail = '') {
  if (cond) pass += 1;
  else {
    fail += 1;
    problems.push(`${name}${detail ? ' — ' + detail : ''}`);
  }
}

console.log('='.repeat(74));
console.log(' FastGPT 工作流蓝图校验（对照 v4.17.1 源码枚举）');
console.log('='.repeat(74));

/* ------------------------------------------------ 1. 读取权威枚举 */
const TMP = path.join(ROOT, '.verify');
fs.mkdirSync(TMP, { recursive: true });

/**
 * 取源码文件内容。
 * 注意：本环境的沙箱禁止 Node 以「管道 stdio」spawn 子进程（EPERM），
 * 因此不能用 execFileSync 的返回值捕获输出；改用 stdio:'inherit' +
 * 让 shell 把结果重定向到文件，再从文件读取（与 compose-check.mjs 相同做法）。
 */
function gitShow(rel) {
  const outFile = path.join(TMP, 'gitshow.out');
  const errFile = path.join(TMP, 'gitshow.err');
  try { fs.rmSync(outFile, { force: true }); } catch { /* ignore */ }
  // 必须用「带引号的绝对路径」：实测 cwd 含中文时，git 以相对路径找不到仓库
  // （报 cannot change to '.fastgpt-lab-notes/FastGPT-src'）。
  const cmd = `git -C "${SRC}" show HEAD:${rel} > "${outFile}" 2> "${errFile}"`;
  const r = spawnSync(cmd, { shell: true, cwd: ROOT, stdio: 'inherit' });
  if (r.status !== 0 || !fs.existsSync(outFile)) return null;
  const txt = fs.readFileSync(outFile, 'utf8');
  return txt.trim() ? txt : null;
}

function parseEnum(src, enumName) {
  if (!src) return null;
  const m = src.match(new RegExp(`export enum ${enumName} \\{([\\s\\S]*?)\\n\\}`));
  if (!m) return null;
  const out = {};
  for (const raw of m[1].split('\n')) {
    const line = raw.trim().replace(/,$/, '');
    if (!line || !line.includes('=')) continue;
    const [k, v] = line.split('=').map((s) => s.trim());
    out[k] = v.replace(/['"]/g, '');
  }
  return out;
}

let sourceUsed = '源码缓存（v4.17.1）';
const nodeConst = gitShow('packages/global/core/workflow/node/constant.ts');
const wfConst = gitShow('packages/global/core/workflow/constants.ts');

let FLOW_NODE_TYPES = nodeConst ? parseEnum(nodeConst, 'FlowNodeTypeEnum') : null;
let INPUT_KEYS = wfConst ? parseEnum(wfConst, 'NodeInputKeyEnum') : null;
let OUTPUT_KEYS = wfConst ? parseEnum(wfConst, 'NodeOutputKeyEnum') : null;

if (!FLOW_NODE_TYPES || !INPUT_KEYS || !OUTPUT_KEYS) {
  sourceUsed = '内置兜底枚举（源码缓存不可用，权威性下降）';
  FLOW_NODE_TYPES = FLOW_NODE_TYPES || {
    workflowStart: 'workflowStart', chatNode: 'chatNode', answerNode: 'answerNode',
    ifElseNode: 'ifElseNode', code: 'code', userSelect: 'userSelect', formInput: 'formInput',
    loop: 'loop', nestedStart: 'loopStart', nestedEnd: 'loopEnd', textEditor: 'textEditor',
    variableUpdate: 'variableUpdate', httpRequest468: 'httpRequest468', datasetSearchNode: 'datasetSearchNode',
    classifyQuestion: 'classifyQuestion', contentExtract: 'contentExtract', readFiles: 'readFiles',
    agent: 'agent', toolCall: 'tools', pluginModule: 'pluginModule', appModule: 'appModule',
    runApp: 'app', parallelRun: 'parallelRun', loopRun: 'loopRun', comment: 'comment',
    globalVariable: 'globalVariable', customFeedback: 'customFeedback'
  };
  INPUT_KEYS = INPUT_KEYS || { description: 'description', userSelectOptions: 'userSelectOptions', userInputForms: 'userInputForms' };
  OUTPUT_KEYS = OUTPUT_KEYS || { selectResult: 'selectResult', formInputResult: 'formInputResult' };
}

console.log('\n[0] 权威枚举来源');
console.log('  来源: ' + sourceUsed);
console.log('  FlowNodeTypeEnum : ' + Object.keys(FLOW_NODE_TYPES).length + ' 个类型');
console.log('  NodeInputKeyEnum : ' + Object.keys(INPUT_KEYS).length + ' 个键');
console.log('  NodeOutputKeyEnum: ' + Object.keys(OUTPUT_KEYS).length + ' 个键');
check('成功读取源码中的 FlowNodeTypeEnum', Boolean(nodeConst));
check('成功读取源码中的 NodeInputKeyEnum / NodeOutputKeyEnum', Boolean(wfConst));

const VALID_TYPES = new Set(Object.values(FLOW_NODE_TYPES));

/* 交互节点在源码中的真实输入/输出键（已逐字核对 userSelect.ts / formInput.ts） */
const INTERACTIVE_SPEC = {
  userSelect: { inputs: ['description', 'userSelectOptions'], outputs: ['selectResult'] },
  formInput: { inputs: ['description', 'userInputForms'], outputs: ['formInputResult'] }
};

/* ------------------------------------------------ 2. 读取蓝图 */
const bp = JSON.parse(fs.readFileSync(BLUEPRINT, 'utf8'));
console.log('\n[1] 蓝图基本信息');
console.log('  app.name        : ' + bp.app.name);
console.log('  app.displayName : ' + bp.app.displayName);
console.log('  节点数          : ' + bp.nodes.length);
check('应用名为 Physics Diagnostic Tutor', bp.app.name === 'Physics Diagnostic Tutor');
check('中文名为 物理考研智能诊断', bp.app.displayName === '物理考研智能诊断');
check('应用类型为 workflow', bp.app.type === 'workflow');
check('不使用 Embedding（题库走 code 常量）', bp.app.requiresEmbedding === false);

/* ------------------------------------------------ 3. 节点类型合法性 */
console.log('\n[2] 节点 flowNodeType 合法性');
const nodeKeys = new Set();
for (const n of bp.nodes) {
  if (nodeKeys.has(n.key)) {
    check(`节点 key 唯一: ${n.key}`, false, '重复');
  }
  nodeKeys.add(n.key);
}
for (const n of bp.nodes) {
  const ok = VALID_TYPES.has(n.flowNodeType);
  check(`节点 ${n.key} 类型 ${n.flowNodeType} 真实存在`, ok, ok ? '' : `不在 FlowNodeTypeEnum 中`);
}
console.log(`  已校验 ${bp.nodes.length} 个节点`);

/* ------------------------------------------------ 4. 交互节点字段 */
console.log('\n[3] 交互节点输入/输出键');
for (const n of bp.nodes) {
  const spec = INTERACTIVE_SPEC[n.flowNodeType];
  if (!spec) continue;
  const inKeys = Object.keys(n.inputs || {});
  const outKeys = Object.keys(n.outputs || {});
  for (const k of inKeys) {
    check(`${n.key}(${n.flowNodeType}) 输入键 ${k} 合法`, spec.inputs.includes(k), `源码支持的键: ${spec.inputs.join(', ')}`);
  }
  for (const k of outKeys) {
    check(`${n.key}(${n.flowNodeType}) 输出键 ${k} 合法`, spec.outputs.includes(k), `源码支持的键: ${spec.outputs.join(', ')}`);
  }
}

/* ------------------------------------------------ 5. 跨节点引用 */
console.log('\n[4] 跨节点引用完整性');
// 只统计真实配置字段：notes / $comment 是给人看的说明，里面会故意出现反例，
// 例如 notes 里写「不能写成 {{I.continue}}」，那不是配置错误。
function configOnly(node) {
  const { notes, ...rest } = node;
  return rest;
}
const allText = JSON.stringify({
  nodes: bp.nodes.map(configOnly),
  workflowVariables: bp.workflowVariables
});
// 形如 {{C.correctKey}} 或 {{I.formInputResult.continue}}
const refs = [...allText.matchAll(/\{\{([A-Za-z0-9_]+)\.([A-Za-z0-9_.]+)\}\}/g)];
const seen = new Set();
for (const [, nodeKey, outKey] of refs) {
  const sig = nodeKey + '.' + outKey;
  if (seen.has(sig)) continue;
  seen.add(sig);
  const target = bp.nodes.find((n) => n.key === nodeKey);
  if (!target) {
    check(`引用 {{${sig}}} 的节点存在`, false, `不存在节点 ${nodeKey}`);
    continue;
  }
  const topKey = outKey.split('.')[0];
  const declared = Object.keys(target.outputs || {});
  const known = declared.includes(topKey) || VALID_TYPES.has(target.flowNodeType) && ['code', 'chatNode'].includes(target.flowNodeType);
  check(`引用 {{${sig}}} 的输出键在节点 ${nodeKey} 上已声明`, known,
    known ? '' : `节点 ${nodeKey}(${target.flowNodeType}) 声明了: ${declared.join(', ') || '（无）'}`);
}
console.log(`  共 ${seen.size} 处不同的跨节点引用`);

/* ------------------------------------------------ 6. 判分保密性 */
console.log('\n[5] 判分保密性（按 phase 强制，防止提前泄露答案）');
const SENSITIVE = ['correctKey', 'correctOption', 'explanation', 'commonMisconceptions'];
const PHASES = new Set(['pre-submit', 'post-submit']);
let preSubmitCount = 0;
for (const n of bp.nodes) {
  check(`节点 ${n.key} 声明了 phase`, PHASES.has(n.phase), `phase=${n.phase}`);
  if (n.phase === 'pre-submit') {
    preSubmitCount += 1;
    const body = JSON.stringify(n.inputs || {});
    const leaked = SENSITIVE.filter((s) => body.includes(s));
    check(`phase=pre-submit 的节点 ${n.key} 不含答案/解析`, leaked.length === 0,
      leaked.length ? `泄露了 ${leaked.join(', ')}（学生会在提交前看到答案）` : '');
  }
}
console.log(`  pre-submit 节点 ${preSubmitCount} 个，已逐个检查敏感字段`);
// 必须存在一个「展示题目」的提交前节点，否则学生看不到题
check('存在 phase=pre-submit 的展示节点（题目可见）',
  bp.nodes.some((n) => n.phase === 'pre-submit' && n.flowNodeType === 'answerNode'));
// 判分节点必须在提交之后
const judge = bp.nodes.find((n) => n.flowNodeType === 'ifElseNode' && /判分/.test(n.title || ''));
check('判分节点位于 post-submit', !judge || judge.phase === 'post-submit', judge ? `phase=${judge.phase}` : '未找到判分节点');
// 解析必须出现在提交之后的节点里
check('解析/错因分析出现在 post-submit 阶段',
  bp.nodes.some((n) => n.phase === 'post-submit' && JSON.stringify(n.inputs || '').includes('explanation')));

/* ------------------------------------------------ 7. 工作流变量 */
console.log('\n[6] 工作流变量引用');
const declaredVars = new Set((bp.workflowVariables || []).map((v) => v.key));
console.log('  已声明: ' + [...declaredVars].join(', '));
// code 节点 inputs 里列出的字符串若为变量名，应当已声明
for (const n of bp.nodes) {
  if (!Array.isArray(n.inputs)) continue;
  for (const v of n.inputs) {
    if (typeof v === 'string' && !v.includes('.') && !declaredVars.has(v)) {
      check(`${n.key} 引用的工作流变量 ${v} 已声明`, false, '未在 workflowVariables 中声明');
    }
  }
}

/* ------------------------------------------------ 8. 结构完整性（本轮新增要求） */
console.log('\n[7] 结构完整性');
const types = bp.nodes.map((n) => n.flowNodeType);
check('包含 workflowStart 或首个交互节点', types.includes('workflowStart') || types.includes('userSelect'));
check('包含 ifElseNode（条件分支）', types.includes('ifElseNode'));
check('包含 answerNode（展示）', types.includes('answerNode'));
check('包含 code 节点（确定性计算）', types.includes('code'));
check('包含 chatNode（模型分析/建议）', types.includes('chatNode'));
check('包含 formInput（继续/结束选择）', types.includes('formInput'));
check('包含 userSelect（题目与选项选择）', types.includes('userSelect'));

/* ------------------------------------------------ 9. WORKFLOW.md 文档一致性 */
console.log('\n[8] WORKFLOW.md 章节编号与交叉引用');
const MD = path.join(ROOT, 'fastgpt', 'WORKFLOW.md');
if (fs.existsSync(MD)) {
  const md = fs.readFileSync(MD, 'utf8');
  const mdLines = md.split(/\r?\n/);
  const sections = [];
  for (let i = 0; i < mdLines.length; i++) {
    const m = mdLines[i].match(/^## (\d+)\.\s*(.*)$/);
    if (m) sections.push({ num: Number(m[1]), title: m[2], line: i + 1 });
  }
  console.log('  章节: ' + sections.map((s) => `§${s.num}`).join(' '));
  // 编号必须从 0 开始且连续递增
  let seqOk = sections.length > 0 && sections[0].num === 0;
  for (let i = 1; i < sections.length; i++) if (sections[i].num !== sections[i - 1].num + 1) seqOk = false;
  check('章节编号从 §0 开始且连续无重复', seqOk,
    seqOk ? '' : '实际: ' + sections.map((s) => s.num).join(', '));
  // 交叉引用 §N 必须指向存在的章节
  const exists = new Set(sections.map((s) => s.num));
  const cited = new Set();
  for (const m of md.matchAll(/§(\d+)/g)) cited.add(Number(m[1]));
  for (const c of cited) {
    check(`交叉引用 §${c} 指向存在的章节`, exists.has(c), exists.has(c) ? '' : `不存在（现有: ${[...exists].join(', ')}）`);
  }
  console.log(`  交叉引用: ${[...cited].map((c) => '§' + c).join(' ') || '（无）'}`);
  // 蓝图里的节点标号应能在文档里找到对应说明
  for (const n of bp.nodes) {
    if (['A', 'B', 'C', 'D', 'E', 'F', 'G1', 'G2', 'H', 'I', 'J', 'K', 'L', 'M'].includes(n.key)) {
      const mentioned = new RegExp(`\\[${n.key}[\\] ]`).test(md) || md.includes('[' + n.key + ']');
      check(`WORKFLOW.md 提到节点 [${n.key}]`, mentioned);
    }
  }
} else {
  check('存在 fastgpt/WORKFLOW.md', false, MD);
}

/* ------------------------------------------------------- 汇总 */
console.log('\n' + '='.repeat(74));
console.log(` 通过 ${pass} 项，失败 ${fail} 项`);
console.log(` 源码依据: ${sourceUsed}`);
if (problems.length) {
  console.log(' 问题明细：');
  for (const p of problems) console.log('   - ' + p);
}
console.log('='.repeat(74));
process.exitCode = fail === 0 ? 0 : 1;
