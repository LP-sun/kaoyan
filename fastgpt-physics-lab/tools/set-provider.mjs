#!/usr/bin/env node
/**
 * set-provider.mjs — 安全地把服务商配置写入 env/.env
 *
 * 为什么需要这个脚本：
 *   密钥不应出现在聊天记录、命令行历史、截图或 Git 里。
 *   本脚本用隐藏输入读取密钥，直接写进已被 .gitignore 忽略的 env/.env，
 *   全程不回显、不打印、不写日志。
 *
 * 用法：
 *
 *   node tools/set-provider.mjs shanghaitech
 *   node tools/set-provider.mjs paratera
 *   node tools/set-provider.mjs custom
 *
 * 脚本只改这 4 个键：GENAI_BASE_URL / GENAI_API_KEY / GENAI_MODEL
 * （以及可选的 GENAI_EMBEDDING_MODEL），其余键原样保留。
 */

import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ENV = path.join(ROOT, 'env', '.env');

const PROVIDERS = {
  shanghaitech: {
    label: '上海科技大学 GenAI 网关',
    base: 'https://genaiapi.shanghaitech.edu.cn/api/v1',
    note: [
      '已实测确认：该域名是真实 API 网关（/api/v1/start 返回 OpenAI 风格错误体）。',
      '注意 1：GET 会 404，必须 POST —— 这是正常的，FastGPT 用的是 POST。',
      '注意 2：该网关**没有** /api/v1/models 端点，所以无法通过接口列出模型，',
      '        模型 ID 必须从学校平台的使用说明里查。',
      '注意 3：如果这个 BASE_URL 最后跑不通，请查看平台文档里真正的调用地址，',
      '        常见形式可能是 .../api/v1/chat/completions 或别的路径。'
    ]
  },
  paratera: {
    label: '并行科技 LLM API',
    base: 'https://llmapi.paratera.com/v1',
    note: [
      '已实测确认：/v1/models 返回标准 OpenAI 401 鉴权错误 → 严格 OpenAI 兼容。',
      '这是目前**最确定可用**的一个，推荐先用它跑通。',
      '设置好密钥后可先运行 node tools/endpoint-probe.mjs 列出全部可用模型 ID。'
    ]
  },
  custom: {
    label: '自定义端点',
    base: '',
    note: ['自行填写 BASE_URL。若不确定端点形态，填完后用 tools/endpoint-probe.mjs 探测。']
  }
};

const which = (process.argv[2] || '').toLowerCase();
const preset = PROVIDERS[which];
if (!preset) {
  console.error('用法: node tools/set-provider.mjs <shanghaitech|paratera|custom>');
  console.error('可选：' + Object.keys(PROVIDERS).join(' | '));
  process.exit(2);
}

if (!fs.existsSync(ENV)) {
  console.error('找不到 ' + ENV);
  console.error('请先从模板创建：cp env/.env.example env/.env');
  process.exit(2);
}

console.log('='.repeat(72));
console.log(' 配置服务商: ' + preset.label);
for (const n of preset.note) console.log('   · ' + n);
console.log('='.repeat(72));

/* ---- 隐藏输入 ---- */
function askHidden(question) {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: true });
    const onData = (char) => {
      // 屏蔽回显：把已输入的字符重画为空
      if (char.toString() === '\r' || char.toString() === '\n') return;
      readline.clearLine(process.stdout, 0);
      readline.cursorTo(process.stdout, 0);
      process.stdout.write(question);
    };
    process.stdin.on('data', onData);
    rl.question(question, (answer) => {
      process.stdin.removeListener('data', onData);
      rl.close();
      process.stdout.write('\n');
      resolve(answer.trim());
    });
  });
}

function askVisible(question, def = '') {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(question + (def ? ` [${def}]` : ''), (a) => {
      rl.close();
      resolve(a.trim() || def);
    });
  });
}

// 注意：这里必须用"是否已定义"来判断，且不能让 await 被无条件求值——
// 无论是 || 还是 ??，只要右侧写成 (await askVisible(...))，空字符串场景下
// 那个 await 依然会被执行并弹出交互提示。所以写成显式分支。
const isSet = (name) => process.env[name] !== undefined;

const base = which === 'custom' ? await askVisible('BASE_URL: ', preset.base) : preset.base;
if (!base) {
  console.error('BASE_URL 不能为空');
  process.exit(2);
}

let key;
if (isSet('GENAI_API_KEY_INPUT')) {
  key = process.env.GENAI_API_KEY_INPUT;
} else {
  key = await askHidden('API Key（输入时不显示，直接回车取消）: ');
}
if (!key) {
  console.error('未输入 Key，已取消，env/.env 未改动。');
  process.exit(2);
}

let model;
if (isSet('GENAI_MODEL_INPUT')) {
  model = process.env.GENAI_MODEL_INPUT;
} else {
  model = await askVisible('模型 ID（如 deepseek-chat / gpt-4o-mini，可留空稍后再填）: ');
}

let embedding;
if (isSet('GENAI_EMBEDDING_MODEL_INPUT')) {
  embedding = process.env.GENAI_EMBEDDING_MODEL_INPUT;
} else {
  embedding = await askVisible('Embedding 模型 ID（学校未提供则留空回车）: ');
}

/* ---- 写回 env/.env，只替换这几个键 ---- */
const original = fs.readFileSync(ENV, 'utf8');
const eol = original.includes('\r\n') ? '\r\n' : '\n';
const lines = original.split(/\r?\n/);
const set = {
  GENAI_BASE_URL: base,
  GENAI_API_KEY: key,
  GENAI_MODEL: model,
  GENAI_EMBEDDING_MODEL: embedding
};
const replaced = {};
const out = lines.map((line) => {
  const m = line.match(/^([A-Z0-9_]+)=/);
  if (m && Object.prototype.hasOwnProperty.call(set, m[1])) {
    replaced[m[1]] = true;
    return `${m[1]}=${set[m[1]]}`;
  }
  return line;
});
// 若模板里没有这些键（理论上不会有），补到文件末尾
const missing = Object.keys(set).filter((k) => !replaced[k]);
if (missing.length) {
  out.push('');
  out.push('# 由 tools/set-provider.mjs 追加');
  for (const k of missing) out.push(`${k}=${set[k]}`);
}

// 备份原文件（同样在 .gitignore 覆盖范围内）
const bak = ENV + '.bak';
fs.copyFileSync(ENV, bak);
fs.writeFileSync(ENV, out.join(eol), 'utf8');

console.log('');
console.log('已写入 ' + path.relative(ROOT, ENV) + '（原文件备份到 ' + path.basename(bak) + '）');
console.log('  GENAI_BASE_URL       = ' + base);
console.log('  GENAI_API_KEY        = ' + (key ? `<已设置，长度 ${key.length}>` : '<未设置>'));
console.log('  GENAI_MODEL          = ' + (model || '<空>'));
console.log('  GENAI_EMBEDDING_MODEL= ' + (embedding || '<空>'));
console.log('');
console.log('确认两件事：');
console.log('  1. env/.env 已被 .gitignore 忽略 —— 不要提交、不要截图、不要粘贴到聊天。');
console.log('  2. 备份文件 ' + path.basename(bak) + ' 同样含密钥，确认它也在忽略范围内。');
console.log('');
console.log('下一步：');
console.log('  node tools/endpoint-probe.mjs ' + base + '   # 列出可用模型（如需）');
console.log('  node tools/genai-conntest.mjs               # 完整连通性测试');
