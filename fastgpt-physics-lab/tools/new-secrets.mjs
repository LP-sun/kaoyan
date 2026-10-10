#!/usr/bin/env node
/**
 * new-secrets.mjs — 生成随机的内部服务密钥
 *
 * 只在本机生成并写入 env/.env，不写入任何远程位置、不打印到聊天。
 *
 * 设计要点（都是部署中踩过的真实坑）：
 *
 * 1. **长度下限 32**：FastGPT 的 plugin 服务在 NODE_ENV=production 下校验
 *      MIN_PRODUCTION_AUTH_TOKEN_LENGTH = 32
 *    低于 32 字符直接抛 `Invalid environment variables: AUTH_TOKEN` 并反复重启。
 *    因此所有 token 类统一生成 48 个字符（hex(24)），留足余量。
 *    同时避开其弱值黑名单：token / changeme / password / secret / default。
 *
 * 2. **字符集选择**：
 *    - 密码类用字母数字：MongoDB 密码若含 @ : / 会让 mongodb:// URI 解析失败。
 *    - token 类用纯 hex：写进 YAML/URL/命令行都不需要转义。
 *
 * 3. **⚠ 卷内凭据不可随意轮换**（重要，会造成数据丢失式故障）：
 *    MONGO / REDIS / PG / MINIO 的凭据在容器**首次启动时就写进了各自的数据卷**：
 *      - MongoDB：管理员账号存在数据目录里
 *      - Redis：requirepass 在 RDB/AOF 里不存，但重启后配置来自 compose
 *      - PostgreSQL：Superuser 密码存在数据目录里
 *      - MinIO：凭据存在其配置中
 *    这些卷已存在时轮换密码会导致服务无法启动（认证失败）。
 *    因此本脚本默认**跳过**它们，只轮换纯 token（容器重启即可生效）。
 *    确实要重置数据库密码时，必须用 --include-volume-bound 明确确认，
 *    并且必须同时删除对应数据卷（本脚本不会替你删，会打印提示）。
 *
 * 用法：
 *   node tools/new-secrets.mjs                      # 只轮换 token（安全，推荐）
 *   node tools/new-secrets.mjs --dry-run            # 只打印将要改哪些键，不写入
 *   node tools/new-secrets.mjs --include-volume-bound   # 连数据库密码一起换（需自行删卷）
 */

import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const ENV = path.join(ROOT, 'env', '.env');

const hex = (bytes) => crypto.randomBytes(bytes).toString('hex');

/**
 * URL 安全密码：仅字母数字。
 * MongoDB 连接串形如 mongodb://user:PASS@host/... ，
 * 密码里出现 @ : / ? # 都会让 URI 解析歧义，故严格限定字符集。
 */
const pwd = (len = 32) => {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let s = '';
  while (s.length < len) {
    for (const b of crypto.randomBytes(len)) {
      if (s.length >= len) break;
      // 拒绝采样，避免取模偏置
      if (b < 248) s += alphabet[b % alphabet.length];
    }
  }
  return s;
};

/** token 类：48 字符 hex，远超 32 下限，且不含需要转义的字符 */
const token = () => hex(24);

/**
 * 可安全轮换：这些只是容器启动参数，重启容器即生效，不落在数据卷里。
 */
const ROTATABLE = {
  FILE_TOKEN_KEY: token(),
  AES256_SECRET_KEY: token(),
  INVOKE_TOKEN_SECRET: token(),
  PLUGIN_TOKEN: token(),
  CONNECTION_GATEWAY_AUTH_TOKEN: token(),
  CODE_SANDBOX_TOKEN: token(),
  AGENT_SANDBOX_PROXY_SECRET: token(),
  AIPROXY_API_TOKEN: token(),
  ROOT_KEY: token(),
  // 登录密码：FastGPT 把它存在 MongoDB 里，改这里只影响"下次重置"，
  // 不会立刻锁死现有账号，但仍建议保持同步。
  DEFAULT_ROOT_PSW: pwd(24)
};

/**
 * 卷内凭据：已初始化过的卷一旦改密码就起不来，默认不碰。
 */
const VOLUME_BOUND = {
  MONGO_ROOT_PASSWORD: () => pwd(32),
  REDIS_PASSWORD: () => pwd(32),
  PG_VECTOR_PASSWORD: () => pwd(32),
  MINIO_ROOT_PASSWORD: () => pwd(32)
};

const argv = process.argv.slice(2);
const dryRun = argv.includes('--dry-run');
const includeVolumeBound = argv.includes('--include-volume-bound');

if (!fs.existsSync(ENV)) {
  console.error(`未找到 ${ENV}`);
  console.error('请先执行：cp env/.env.example env/.env');
  process.exit(1);
}

console.log('='.repeat(72));
console.log(' 内部密钥生成（仅本机，内容不打印）');
console.log('='.repeat(72));

const text0 = fs.readFileSync(ENV, 'utf8');
const present = (k) => new RegExp(`^${k}=`, 'm').test(text0);

const plan = Object.entries(ROTATABLE).map(([k, v]) => [k, v, 'rotate']);
if (includeVolumeBound) {
  for (const [k, gen] of Object.entries(VOLUME_BOUND)) plan.push([k, gen(), 'volume-bound']);
}

console.log('\n将写入以下键（只显示长度，不显示值）：');
for (const [k, v, kind] of plan) {
  const tag = kind === 'volume-bound' ? '  ⚠ 卷内凭据' : '';
  const skip = present(k) ? '' : '  (env/.env 中没有此键，将跳过)';
  console.log(`  ${k.padEnd(32)} 长度=${String(v.length).padStart(3)}${tag}${skip}`);
}

if (!includeVolumeBound) {
  console.log('\n已跳过的卷内凭据（默认不轮换，否则已初始化的数据卷会认证失败）：');
  for (const k of Object.keys(VOLUME_BOUND)) {
    console.log(`  ${k.padEnd(32)} 当前长度=${((text0.match(new RegExp(`^${k}=(.*)$`, 'm')) || [])[1] || '').length}`);
  }
  console.log('  如需轮换它们：node tools/new-secrets.mjs --include-volume-bound');
  console.log('  并且必须同时删除对应数据卷（本脚本不会替你删）。');
}

if (dryRun) {
  console.log('\n--dry-run：未写入任何内容。');
  process.exit(0);
}

let text = text0;
let updated = 0;
const skipped = [];
for (const [k, v] of plan) {
  const re = new RegExp(`^${k}=.*$`, 'm');
  if (re.test(text)) {
    text = text.replace(re, `${k}=${v}`);
    updated += 1;
  } else {
    skipped.push(k);
  }
}

// 备份，便于回滚
const bak = `${ENV}.bak`;
fs.copyFileSync(ENV, bak);
fs.writeFileSync(ENV, text, 'utf8');

console.log('\n' + '='.repeat(72));
console.log(`已更新 ${updated} 个字段 → ${path.relative(ROOT, ENV)}`);
console.log(`原文件已备份到 ${path.basename(bak)}（同样含密钥，已在 .gitignore 中）`);
if (skipped.length) console.log(`跳过（文件中无此键）：${skipped.join(', ')}`);

if (includeVolumeBound) {
  console.log('\n⚠ 你选择了轮换卷内凭据。必须执行以下步骤，否则服务无法启动：');
  console.log('   docker compose --env-file env/.env down');
  console.log('   docker volume rm fastgpt-physics-lab_fastgpt-mongo fastgpt-physics-lab_fastgpt-redis fastgpt-physics-lab_fastgpt-vector fastgpt-physics-lab_fastgpt-minio');
  console.log('   docker compose --env-file env/.env up -d');
  console.log('   注意：这会清空 FastGPT 的全部已有数据（账号、知识库、对话记录）。');
}

console.log('\n改完 token 后让容器重新读取：');
console.log('   docker compose --env-file env/.env up -d');
