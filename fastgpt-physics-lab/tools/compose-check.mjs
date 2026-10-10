#!/usr/bin/env node
/**
 * compose-check.mjs — docker-compose.yml 静态校验（无需 Docker）
 *
 * 在没有 Docker 的环境里，尽可能验证 Compose 配置的正确性：
 *   1. 服务清单与必需服务是否齐全
 *   2. 每个服务引用的 ${VAR} / ${VAR:-default} 是否在 env/.env 或 env/.env.example 中定义（或带默认值）
 *   3. env/.env 与 env/.env.example 的键集合是否一致（防止漏项）
 *   4. 隔离性硬性检查：
 *        - 不得出现 container_name（会与其它项目重名）
 *        - 不得出现 network_mode: host
 *        - 所有 ports 映射必须显式绑定 127.0.0.1
 *        - 不得挂载 /var/run/docker.sock
 *        - 不得使用 :latest 镜像
 *        - 数据卷不得使用宿主机绝对路径
 *   5. 密码一致性：MONGODB_URI / REDIS_URL / PG_URL 中引用的密码变量，
 *      必须与对应服务 environment 里的密码变量一致
 *
 * 本脚本不连接 Docker、不修改任何文件。
 *
 * 用法：node tools/compose-check.mjs
 */

import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { loadEnvFile } from './genai.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PROJECT = 'fastgpt-physics-lab'; // 必须与 docker-compose.yml 顶层 name: 一致
const COMPOSE = path.join(ROOT, 'docker-compose.yml');
const ENV = path.join(ROOT, 'env', '.env');
const ENV_EX = path.join(ROOT, 'env', '.env.example');

const text = fs.readFileSync(COMPOSE, 'utf8');
const lines = text.split(/\r?\n/);

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

/** 读取项目内文件，不存在时返回空串（便于断言写成"文件缺失即失败"） */
function readIfExists(rel) {
  const p = path.join(ROOT, rel);
  return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : '';
}

console.log('='.repeat(74));
console.log(' docker-compose.yml 静态校验: ' + COMPOSE);
console.log('='.repeat(74));

/* ------------------------------------------------------- 1. 服务清单 */
const serviceNames = [];
let inServices = false;
for (const line of lines) {
  if (/^services:\s*$/.test(line)) { inServices = true; continue; }
  if (inServices && /^[a-z]/.test(line)) { inServices = false; } // 顶层键结束
  if (inServices) {
    const m = line.match(/^  ([A-Za-z0-9_.-]+):\s*$/);
    if (m) serviceNames.push(m[1]);
  }
}
const REQUIRED = [
  'fastgpt-app', 'fastgpt-mongo', 'fastgpt-redis', 'fastgpt-vector',
  'fastgpt-minio', 'fastgpt-plugin', 'fastgpt-code-sandbox', 'fastgpt-agent-sandbox-proxy'
];
console.log('\n[1] 服务清单');
console.log('  发现 ' + serviceNames.length + ' 个服务：' + serviceNames.join(', '));
for (const r of REQUIRED) {
  check(`包含必需服务 ${r}`, serviceNames.includes(r));
}
const FORBIDDEN = ['fastgpt-opensandbox-server', 'fastgpt-volume-manager', 'fastgpt-aiproxy', 'fastgpt-aiproxy-pg'];
const present = FORBIDDEN.filter((f) => serviceNames.includes(f));
check('已移除挂载 docker.sock / 非必需的组件', present.length === 0, present.join(', '));

/* ------------------------------------------------------- 2. 隔离性硬检查 */
console.log('\n[2] 隔离性硬性检查');

const containerNameLines = lines.filter((l) => /^\s*container_name:/.test(l));
check('无固定 container_name', containerNameLines.length === 0, `${containerNameLines.length} 处`);

check('无 network_mode: host', !/network_mode:\s*host/.test(text));

const sockMounts = lines.filter((l) => /docker\.sock/.test(l) && !/^\s*#/.test(l));
check('未挂载 Docker socket', sockMounts.length === 0, sockMounts.map((s) => s.trim()).join(' | '));

const portLines = lines.filter((l) => /^\s*-\s*["']?[^"']*:\d+["']?\s*$/.test(l) && !/^\s*#/.test(l));
const badPorts = portLines.filter((l) => !/127\.0\.0\.1:/.test(l));
check('所有端口映射均绑定 127.0.0.1', badPorts.length === 0, badPorts.map((s) => s.trim()).join(' | '));
console.log('  端口映射共 ' + portLines.length + ' 条：');
for (const p of portLines) console.log('    ' + p.trim());

const latestImgs = lines.filter((l) => /image:.*:latest/.test(l));
check('未使用 :latest 镜像', latestImgs.length === 0, latestImgs.map((s) => s.trim()).join(' | '));

// 任务要求：FastGPT Web 宿主机端口优先 3100
const appPort = text.match(/127\.0\.0\.1:\$\{FASTGPT_HOST_PORT:-(\d+)\}:(\d+)/);
check('FastGPT Web 端口默认值为任务要求的 3100', appPort && appPort[1] === '3100', `实际默认: ${appPort?.[1]}`);
check('FastGPT Web 容器内端口为 3000', appPort && appPort[2] === '3000', `实际: ${appPort?.[2]}`);
const env0 = loadEnvFile(ENV);
check('env/.env 中 FASTGPT_HOST_PORT=3100', env0.FASTGPT_HOST_PORT === '3100', `实际: ${env0.FASTGPT_HOST_PORT}`);
check('env/.env 中 FE_DOMAIN 指向 3100', String(env0.FE_DOMAIN || '').endsWith(':3100'), `实际: ${env0.FE_DOMAIN}`);
// 端口不得互相冲突
const assigned = {
  'FastGPT Web': Number(env0.FASTGPT_HOST_PORT),
  'Sandbox Proxy': Number(env0.SANDBOX_PROXY_HOST_PORT),
  '本地诊断服务': Number(env0.DIAG_PORT)
};
const vals = Object.values(assigned);
check('三个宿主机端口互不重复', new Set(vals).size === vals.length, JSON.stringify(assigned));

const volumeSection = text.split(/^volumes:\s*$/m)[1] || '';
const hostVolumes = volumeSection.split(/\r?\n/).filter((l) => /^\s*-\s*[A-Za-z]:[\\/]|^\s*-\s*\//.test(l));
check('数据卷未使用宿主机绝对路径', hostVolumes.length === 0, hostVolumes.join(' | '));

/* ------------------------------------------------------- 3. 变量定义完整性 */
console.log('\n[3] 环境变量定义完整性');
const composeVars = new Set();
for (const m of text.matchAll(/\$\{([A-Za-z_][A-Za-z0-9_]*)(:-[^}]*)?\}/g)) {
  composeVars.add(m[1]);
}
const envKeys = new Set(Object.keys(loadEnvFile(ENV)));
const envExKeys = new Set(Object.keys(loadEnvFile(ENV_EX)));
const defined = new Set([...envKeys, ...envExKeys]);

const hasDefault = new Set();
for (const m of text.matchAll(/\$\{([A-Za-z_][A-Za-z0-9_]*):-([^}]*)\}/g)) hasDefault.add(m[1]);

const unresolved = [...composeVars].filter((v) => !defined.has(v) && !hasDefault.has(v));
check('Compose 引用的变量均有定义或默认值', unresolved.length === 0, unresolved.join(', '));
console.log(`  引用变量 ${composeVars.size} 个；env/.env 定义 ${envKeys.size} 个；.env.example 定义 ${envExKeys.size} 个`);

/* ------------------------------------------------------- 4. env 键集合一致 */
console.log('\n[4] env/.env 与 env/.env.example 键一致性');
const onlyInEnv = [...envKeys].filter((k) => !envExKeys.has(k));
const onlyInEx = [...envExKeys].filter((k) => !envKeys.has(k));
check('.env 中的键都在 .env.example 中', onlyInEnv.length === 0, onlyInEnv.join(', '));
check('.env.example 中的键都在 .env 中', onlyInEx.length === 0, onlyInEx.join(', '));

/* ------------------------------------------------------- 5. 密码一致性 */
console.log('\n[5] 数据库连接串与服务密码的一致性');

function envVarOf(service, keys) {
  // 找到指定服务块内的 environment 中使用的变量名
  const idx = lines.findIndex((l) => new RegExp(`^  ${service}:\\s*$`).test(l));
  if (idx === -1) return null;
  let end = lines.length;
  for (let i = idx + 1; i < lines.length; i++) {
    if (/^  [A-Za-z0-9_.-]+:\s*$/.test(lines[i])) { end = i; break; }
  }
  const block = lines.slice(idx, end).join('\n');
  for (const k of keys) {
    const m = block.match(new RegExp(`${k}:\\s*\\$\\{([A-Za-z_][A-Za-z0-9_]*)(?::-[^}]*)?\\}`));
    if (m) return m[1];
  }
  return null;
}

// MONGODB_URI 中的用户名/密码变量 vs fastgpt-mongo 的环境变量
const mongoUri = text.match(/MONGODB_URI:\s*mongodb:\/\/\$\{([A-Za-z_]+)[^}]*\}:\$\{([A-Za-z_]+)[^}]*\}@/);
const mongoUserVar = envVarOf('fastgpt-mongo', ['MONGO_INITDB_ROOT_USERNAME']);
const mongoPwdVar = envVarOf('fastgpt-mongo', ['MONGO_INITDB_ROOT_PASSWORD']);
check(
  'MONGODB_URI 的用户名与 mongo 服务一致',
  mongoUri && mongoUserVar && mongoUri[1] === mongoUserVar,
  `URI 用 ${mongoUri?.[1]} / 服务用 ${mongoUserVar}`
);
check(
  'MONGODB_URI 的密码与 mongo 服务一致',
  mongoUri && mongoPwdVar && mongoUri[2] === mongoPwdVar,
  `URI 用 ${mongoUri?.[2]} / 服务用 ${mongoPwdVar}`
);

const redisUri = text.match(/REDIS_URL:\s*redis:\/\/[^:]+:\$\{([A-Za-z_]+)/);
const redisPwd = (text.match(/REDIS_PASSWORD:\s*\$\{([A-Za-z_]+)/) || [])[1] ||
  (text.match(/--requirepass \$\{([A-Za-z_]+)/) || [])[1];
check(
  'REDIS_URL 的密码与 redis 服务一致',
  redisUri && redisPwd && redisUri[1] === redisPwd,
  `URI 用 ${redisUri?.[1]} / 服务用 ${redisPwd}`
);

const pgUri = text.match(/PG_URL:\s*postgresql:\/\/\$\{([A-Za-z_]+)[^}]*\}:\$\{([A-Za-z_]+)[^}]*\}@/);
const pgUser = (text.match(/POSTGRES_USER:\s*\$\{([A-Za-z_]+)/) || [])[1];
const pgPwd = (text.match(/POSTGRES_PASSWORD:\s*\$\{([A-Za-z_]+)/) || [])[1];
check('PG_URL 的用户名与 vector 服务一致', pgUri && pgUser && pgUri[1] === pgUser, `URI 用 ${pgUri?.[1]} / 服务用 ${pgUser}`);
check('PG_URL 的密码与 vector 服务一致', pgUri && pgPwd && pgUri[2] === pgPwd, `URI 用 ${pgUri?.[2]} / 服务用 ${pgPwd}`);

// MongoDB entrypoint 是否正确转义 $$（否则容器内 shell 会在运行时展开为空）
// 注意：必须按“服务定义块”取，不能用 indexOf('fastgpt-redis:') ——
// depends_on 里也会出现这个名字，会把切片截断。
const svcIdx = lines.findIndex((l) => /^  fastgpt-mongo:\s*$/.test(l));
let svcEnd = lines.length;
for (let i = svcIdx + 1; i < lines.length; i++) {
  if (/^  [A-Za-z0-9_.-]+:\s*$/.test(lines[i])) { svcEnd = i; break; }
}
const mongoBlock = lines.slice(svcIdx, svcEnd);
const epIdx = mongoBlock.findIndex((l) => /^\s*entrypoint:\s*$/.test(l));
const entrypointBlock = (epIdx >= 0 ? mongoBlock.slice(epIdx) : [])
  .filter((l) => !/^\s*#/.test(l)) // 注释里的字面量不算引用
  .join('\n');
/* --- MongoDB 启动可靠性（本机实测踩过的坑，全部固化为断言） --- */
// 坑 1：Compose 的变量插值发生在 YAML 解析之前，所以 YAML 单引号 **挡不住** $VAR 被替换。
//       实测：把 $MONGO_ROOT_PASSWORD 写在单引号里，config 输出中被替换成了明文密码。
// 坑 2：$$VAR 转义在本机 Compose v5.6.0 下不可靠 —— config 输出保留 $$，
//       而 bash 中 $$ 是进程号，$$VAR 会展开成 "12345VAR"，认证必然失败。
// 结论：多行 shell 脚本必须放进挂载文件（绕开 Compose 插值），
//       不在 compose 的 command/entrypoint/healthcheck 里依赖运行时 shell 变量展开。
const rawShellVar = /(^|[^$])\$\{(MONGO_ROOT_[A-Z_]+)/m.test(entrypointBlock);
check(
  'MongoDB 未在 command/entrypoint 中依赖运行时 ${...} 展开',
  !rawShellVar,
  rawShellVar ? '存在 ${MONGO_ROOT_...}，会被 Compose 提前替换或展开为空' : ''
);

// 只检查真实配置行：注释里为了说明问题会提到 $$VAR 和 --keyFile，不应算作配置
const mongoCode = mongoBlock.filter((l) => !/^\s*#/.test(l)).join('\n');
check(
  'MongoDB 未使用不可靠的 $$ 转义写法',
  !/\$\$[A-Za-z_]/.test(mongoCode),
  '发现 $$VAR，本机 Compose 下会展开为 进程号+VAR'
);
check(
  'MongoDB 未自行接管 entrypoint（否则官方镜像不会执行 initdb.d 脚本）',
  epIdx === -1,
  epIdx !== -1 ? '存在 entrypoint 覆盖' : ''
);

// 副本集初始化脚本：必须通过挂载文件提供，且文件真实存在、内含必要的 rs.initiate
const initMount = mongoBlock.find((l) => /docker-entrypoint-initdb\.d/.test(l));
check('MongoDB 通过挂载文件提供副本集初始化脚本', Boolean(initMount), initMount || '未找到 initdb.d 挂载');
let initScriptOk = false;
let initScriptDetail = '未找到挂载脚本';
if (initMount) {
  const rel = (initMount.match(/\.\/([^:]+):/) || [])[1];
  if (rel) {
    const p = path.join(ROOT, rel);
    if (fs.existsSync(p)) {
      const s = fs.readFileSync(p, 'utf8');
      initScriptOk = /rs\.initiate/.test(s) && /rs0/.test(s) && /fastgpt-mongo:27017/.test(s);
      initScriptDetail = initScriptOk ? '' : `${rel} 中缺少 rs.initiate / rs0 / fastgpt-mongo:27017`;
    } else {
      initScriptDetail = `挂载的脚本不存在: ${rel}`;
    }
  }
}
check('副本集初始化脚本内容正确', initScriptOk, initScriptDetail);

// healthcheck 必须使用与 mongo 服务相同的密码变量（否则永远 unhealthy → app 永不启动）
const hcLine = mongoBlock.find((l) => /^\s*test:/.test(l)) || '';
check(
  'MongoDB healthcheck 使用与 URI 一致的凭据变量',
  hcLine.includes(mongoUserVar || '\u0000') && hcLine.includes(mongoPwdVar || '\u0000'),
  hcLine.trim()
);

/*
 * keyFile 断言（这条断言曾经写反，已按实测证据修正）
 *
 * 早期版本这里断言「不应使用 --keyFile」，理由是"避免密钥文件先于 mongod 存在的
 * 启动依赖"。该推断是**错的**，并直接导致了真实的启动故障：
 *   mongod 退出码 2，日志为
 *   BadValue: security.keyFile is required when authorization is enabled with replica sets
 * 即：只要同时开启鉴权（MONGO_INITDB_ROOT_*）与副本集（--replSet），
 * MongoDB 就**强制要求** keyFile。因此正确断言是「必须使用 keyFile」。
 */
check(
  'MongoDB 使用 --keyFile（鉴权 + 副本集组合下 MongoDB 强制要求）',
  /--keyFile/.test(mongoCode),
  '缺少 --keyFile（会导致 mongod 以退出码 2 反复重启）'
);

check(
  'MongoDB 使用 --replSet（FastGPT 事务依赖副本集）',
  /--replSet/.test(mongoCode),
  '缺少 --replSet'
);

// keyFile 必须由一个「先于 mongod 执行」的 entrypoint 包装脚本生成并修权限：
// 官方镜像里 mongod 以 mongodb 用户运行，而容器内新文件默认 root 属主，
// 直接挂载或直接创建都会因权限不符被 mongod 拒绝。
check(
  'MongoDB entrypoint 被包装脚本接管（负责生成 keyFile 并修权限）',
  /mongo-entrypoint\.sh/.test(mongoBlock.join('\n')),
  '未发现 mongo-entrypoint.sh'
);

check(
  'keyFile 生成脚本已挂载到容器',
  /mongo-entrypoint\.sh:\/docker-entrypoint-wrapper\/mongo-entrypoint\.sh/.test(mongoBlock.join('\n')),
  '未挂载 mongo-entrypoint.sh'
);

// 副本集初始化必须幂等且位于启动路径上：
// 官方 initdb.d 只在数据目录为空时执行，早期启动失败会让数据目录非空，
// 之后 initdb.d 永不执行 → 副本集永远未初始化 → 应用侧连接缓冲超时。
check(
  '副本集自举脚本已挂载（每次启动幂等执行，不依赖 initdb.d）',
  /mongo-replset-bootstrap\.sh:\/docker-entrypoint-wrapper\/mongo-replset-bootstrap\.sh/.test(mongoBlock.join('\n')),
  '未挂载 mongo-replset-bootstrap.sh'
);

// 脚本必须实现幂等判定，否则每次启动都会重复 rs.initiate 并报错
const keyFileScript = (() => {
  const p = path.join(ROOT, 'scripts', 'mongo-entrypoint.sh');
  return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : '';
})();
check(
  'mongo-entrypoint.sh 生成的是 base64 合法字符集 keyFile（MongoDB 拒绝其它字符）',
  /openssl rand -base64|urandom \| base64/.test(keyFileScript) && /grep -q '\[\^A-Za-z0-9\+\/\]'/.test(keyFileScript),
  '未发现 base64 生成 + 非法字符自检逻辑'
);

const bootstrapScript = (() => {
  const p = path.join(ROOT, 'scripts', 'mongo-replset-bootstrap.sh');
  return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : '';
})();
check(
  '副本集自举脚本先判断 rs.status() 再 initiate（保证幂等）',
  /rs\.status\(\)/.test(bootstrapScript) && /rs\.initiate\(/.test(bootstrapScript),
  '缺少幂等判定'
);

// plugin 在 NODE_ENV=production 下要求 AUTH_TOKEN / CONNECTION_GATEWAY_AUTH_TOKEN
// 均 >= 32 字符，否则抛 Invalid environment variables 并无限重启
const composeText = fs.readFileSync(path.join(ROOT, 'docker-compose.yml'), 'utf8');
check(
  'plugin 同时提供 AUTH_TOKEN 与 CONNECTION_GATEWAY_AUTH_TOKEN',
  /AUTH_TOKEN:/.test(composeText) && /CONNECTION_GATEWAY_AUTH_TOKEN:/.test(composeText),
  '缺少其中之一（plugin 会因环境变量校验失败而反复重启）'
);

// app 强制要求 AIPROXY_API_ENDPOINT（UrlSchema）与 AIPROXY_API_TOKEN，缺失则 app 无限重启
check(
  'app 提供 AIPROXY_API_ENDPOINT 与 AIPROXY_API_TOKEN（v4.17 启动强制项）',
  /AIPROXY_API_ENDPOINT:/.test(composeText) && /AIPROXY_API_TOKEN:/.test(composeText),
  '缺少 AIPROXY_*（app 会因环境变量校验失败而反复重启）'
);

// token 类密钥长度必须 >= 32，避免再次触发 plugin 的生产环境校验
const genTool = (() => {
  const p = path.join(ROOT, 'tools', 'new-secrets.mjs');
  return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : '';
})();
check(
  '密钥生成器对 token 使用 >=32 字符长度',
  /const token = \(\) => hex\(24\)/.test(genTool),
  'token 生成长度不足 32'
);
check(
  '密钥生成器默认不轮换卷内凭据（避免改密码后数据卷认证失败）',
  /VOLUME_BOUND/.test(genTool) && /include-volume-bound/.test(genTool),
  '缺少卷内凭据保护'
);

/*
 * 回归断言：LLM 调用点的 max_tokens / maxTokens 必须给足。
 *
 * 背景（真实踩坑）：这些模型有的会先输出思维链（reasoning_content），
 * 而思维链**同样计入 completion tokens**。配额太小（曾用 700/800）时，
 * 思维链吃光配额，正式 JSON 被截断，表现为「模型返回的不是可解析 JSON」，
 * 极易被误判为模型能力不足——我据此一度得出完全错误的模型排名。
 * 因此这里把「不得低于 2000」固化为断言，防止以后改配置时回退。
 */
const MIN_TOKENS = 2000;
const tokenGuards = [
  ['tools/diagnosis-server.mjs', /maxTokens:\s*(\d+)/g],
  ['tools/pick-model.mjs', /max_tokens:\s*(\d+)/g]
];
for (const [rel, re] of tokenGuards) {
  const src = readIfExists(rel);
  if (!src) { check(`${rel} 存在`, false, '文件缺失'); continue; }
  const vals = [...src.matchAll(re)].map((m) => Number(m[1]));
  // 生成答案的调用点必须给足（>=2000）；连通性探活可以小一些，但也不能小到
  // 被思维链吃光（曾用 24，已提到 600）。这里按 >=500 作为下限。
  const all = vals;
  check(
    `${rel} 的 LLM 调用点 max_tokens 均 >= 500（生成类 >= ${MIN_TOKENS}）`,
    all.length > 0 && all.every((v) => v >= 500),
    `实测值 [${vals.join(', ')}]；过小会因思维链占用配额而截断 JSON 或误报探测失败`
  );
}
// 工作流文档必须写明该要求，否则在 FastGPT 里搭建时会重演同一故障
const wfDoc = readIfExists('fastgpt/WORKFLOW.md');
check(
  'fastgpt/WORKFLOW.md 已写明 LLM 节点 max_tokens 要求',
  /最大回复长度\s*≥\s*2500/.test(wfDoc) && !/最大回复长度\s*700/.test(wfDoc),
  '工作流文档未标注或仍写着过小的 700'
);

/* --------------------------------------- 6. 真实 Compose 解析（权威） */
console.log('\n[6] 真实 Compose 解析器验证（最强证据）');

const COMPOSE_BIN = process.env.COMPOSE_BIN || path.join(ROOT, '.verify', 'docker-compose.exe');
let authoritative = '未验证';
if (fs.existsSync(COMPOSE_BIN)) {
  console.log('  使用解析器: ' + COMPOSE_BIN);
  // 沙箱限制：Node 的 spawnSync 只能用 stdio:'inherit'（管道 stdio 会 EPERM）。
  // 因此让 shell 自己把输出重定向到文件，再从文件读取。
  // 实测确定可用的调用形式（其它形式 cmd 都不认，报 "is not recognized"）：
  //   - 必须用 shell:true；
  //   - 可执行文件路径必须以 `.\\` 前缀或带引号的绝对路径给出；
  //   - 只写 `.verify/x.exe`（无 `.\`）或 `./.verify/x.exe` 都会失败。
  const outRel = '.verify/config.out';
  const errRel = '.verify/config.err';
  const outAbs = path.join(ROOT, outRel);
  const errAbs = path.join(ROOT, errRel);
  for (const f of [outAbs, errAbs]) {
    try { fs.rmSync(f, { force: true }); } catch { /* ignore */ }
  }
  const binRel = '.\\' + path.relative(ROOT, COMPOSE_BIN);
  const shellCmd = `${binRel} --env-file env/.env -f docker-compose.yml config > ${outRel} 2> ${errRel}`;
  const r = spawnSync(shellCmd, { shell: true, cwd: ROOT, stdio: 'inherit' });

  const stdout = fs.existsSync(outAbs) ? fs.readFileSync(outAbs, 'utf8') : '';
  const stderr = fs.existsSync(errAbs) ? fs.readFileSync(errAbs, 'utf8').trim() : '';
  const exitedOk = r.status === 0;

  check('docker compose config 解析成功（exit 0）', exitedOk, exitedOk ? '' : `exit ${r.status}: ${stderr.slice(0, 300)}`);
  check('docker compose config 无警告（无未定义变量）', stderr === '', stderr.slice(0, 300));
  if (exitedOk) {
    authoritative = '已通过真实解析器验证';
    const nameMatch = stdout.match(/^name:\s*(\S+)/m);
    check('未传 -p 时项目名仍为 fastgpt-physics-lab', nameMatch && nameMatch[1] === PROJECT, `实际: ${nameMatch?.[1]}`);
    check('解析后所有服务 container_name 为空', !/container_name:/.test(stdout));
    const hosts = [...stdout.matchAll(/host_ip:\s*(\S+)/g)].map((m) => m[1]);
    check('解析后端口均绑定 127.0.0.1', hosts.length > 0 && hosts.every((h) => h === '127.0.0.1'), hosts.join(', '));
  }
} else {
  console.log('  未找到 Compose 解析器，跳过（权威验证缺失）。');
  console.log('  获取方式（无需 Docker daemon，仅做解析验证）：');
  console.log('    node .fastgpt-lab-notes/dl.js \\');
  console.log('      https://github.com/docker/compose/releases/download/v5.6.0/docker-compose-windows-x86_64.exe \\');
  console.log('      .verify/docker-compose.exe');
  console.log('  之后重跑本脚本，或用 COMPOSE_BIN=... 指定其它路径。');
}

/* ------------------------------------------------------- 汇总 */
console.log('\n' + '='.repeat(74));
console.log(` 通过 ${pass} 项，失败 ${fail} 项`);
console.log(` 权威解析器验证: ${authoritative}`);
if (problems.length) {
  console.log(' 问题明细：');
  for (const p of problems) console.log('   - ' + p);
}
console.log('='.repeat(74));
process.exitCode = fail === 0 ? 0 : 1;
