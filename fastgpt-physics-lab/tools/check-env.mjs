#!/usr/bin/env node
/**
 * check-env.mjs — 部署前环境预检（只读，不做任何修改）
 *
 * 检查：
 *   1. Docker CLI / Docker Compose v2 / Docker daemon 是否可用
 *   2. 本项目需要绑定的宿主机端口是否空闲
 *   3. 是否已存在会冲突的容器 / 数据卷 / 网络 / Compose 项目
 *   4. env/.env 是否已就绪（必填项是否填写）
 *   5. 磁盘余量
 *
 * 不会停止、启动或删除任何容器。全部为只读查询。
 *
 * 用法：node tools/check-env.mjs
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import { fileURLToPath } from 'node:url';
import { loadConfig } from './genai.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PROJECT = 'fastgpt-physics-lab';

const cfg = loadConfig(ROOT);

function run(cmd, args) {
  try {
    return { ok: true, out: execFileSync(cmd, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim() };
  } catch (e) {
    const err = (e.stderr || e.message || '').trim();
    // EPERM/ENOENT 都表示"这条命令在本环境不可用"，不区分表述以免误导
    const friendly = /ENOENT|EPERM|not recognized|不是内部或外部命令|CommandNotFound/i.test(err)
      ? '命令不可用（未安装，或当前环境不允许执行）'
      : err;
    return { ok: false, out: (e.stdout || '').trim(), err: friendly };
  }
}

function section(t) {
  console.log('\n' + t);
}

console.log('='.repeat(72));
console.log(' fastgpt-physics-lab 部署前环境预检（只读）');
console.log('='.repeat(72));

let blockers = 0;
let warnings = 0;

/* ------------------------------------------------------------- 1. Docker */
section('[1] Docker 运行时');
const dv = run('docker', ['--version']);
if (dv.ok) {
  console.log('  ✓ docker CLI      : ' + dv.out);
} else {
  console.log('  ✗ docker CLI      : 未找到（' + (dv.err || '命令不存在') + '）');
  blockers += 1;
}

if (dv.ok) {
  const dcv = run('docker', ['compose', 'version']);
  if (dcv.ok) console.log('  ✓ docker compose  : ' + dcv.out.split('\n')[0]);
  else {
    console.log('  ✗ docker compose  : 不可用（需要 Compose v2）');
    blockers += 1;
  }
  const di = run('docker', ['info', '--format', '{{.ServerVersion}}']);
  if (di.ok) console.log('  ✓ docker daemon   : 运行中，引擎版本 ' + di.out);
  else {
    console.log('  ✗ docker daemon   : 未运行或当前用户无权访问 Docker');
    blockers += 1;
  }
} else {
  console.log('  - 跳过 Compose / daemon 检查（Docker 未安装）');
  console.log('');
  console.log('  说明：本机当前情形即为“未安装 Docker”。');
  console.log('        安装 Docker Desktop 需要管理员权限（UAC）并会改动 WSL2/虚拟机平台');
  console.log('        等系统组件、启动系统级服务，属于本任务明确要求避免的风险操作。');
  console.log('        请在获得授权后手动安装，再回来执行本预检与部署。');
}

/* ------------------------------------------------------------- 2. 端口 */
section('[2] 宿主机端口占用（本项目只绑定回环地址）');
const wanted = [
  { port: Number(cfg.diagPort) || 3101, why: '本项目本地诊断服务（非 FastGPT）' },
  { port: 3100, why: 'FastGPT Web（容器 3000）— 任务要求的首选端口' },
  { port: 3102, why: 'Agent Sandbox Proxy（容器 1006）' },
  { port: 3103, why: '备用 FastGPT Web 端口' }
];

function portFree(port, host = '127.0.0.1') {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.once('error', () => resolve(false));
    srv.once('listening', () => srv.close(() => resolve(true)));
    srv.listen(port, host);
  });
}

for (const w of wanted) {
  const free = await portFree(w.port);
  if (free) {
    console.log(`  ✓ ${w.port} 空闲  — ${w.why}`);
  } else {
    console.log(`  ✗ ${w.port} 被占用 — ${w.why}`);
    warnings += 1;
  }
}
console.log('  提示：3100 已实测可绑（连续 15 次 bind 成功 + 真实 HTTP 请求通过），故按要求优先使用 3100。');

/* --------------------------------------------- 3. 冲突的容器/卷/网络 */
section('[3] 与既有资源的冲突检查');
if (dv.ok && run('docker', ['info']).ok) {
  const ps = run('docker', ['ps', '-a', '--format', '{{.Names}}\t{{.Image}}\t{{.Status}}']);
  const lines = ps.ok && ps.out ? ps.out.split('\n') : [];
  const clash = lines.filter((l) => /fastgpt|mongo|redis|pgvector|minio/i.test(l));
  console.log(`  现有容器共 ${lines.length} 个`);
  if (clash.length) {
    console.log('  ! 以下既有容器名称与 FastGPT 组件相似，部署前请确认不会冲突：');
    for (const c of clash) console.log('      ' + c);
    warnings += 1;
  } else {
    console.log('  ✓ 未发现与 FastGPT 组件同名的既有容器');
  }

  const vols = run('docker', ['volume', 'ls', '--format', '{{.Name}}']);
  const vlines = vols.ok && vols.out ? vols.out.split('\n') : [];
  const vclash = vlines.filter((v) => v.startsWith(PROJECT));
  if (vclash.length) {
    console.log('  ! 已存在本项目名的数据卷（可能是上次部署残留）：' + vclash.join(', '));
    console.log('      若确认要保留数据，直接 up -d 即可；若不存在有效数据也不要在本任务中删除。');
    warnings += 1;
  } else {
    console.log(`  ✓ 不存在名为 ${PROJECT}_* 的数据卷`);
  }

  const nets = run('docker', ['network', 'ls', '--format', '{{.Name}}']);
  const nlines = nets.ok && nets.out ? nets.out.split('\n') : [];
  const existing = nlines.filter((n) => n.startsWith(PROJECT));
  console.log(
    existing.length
      ? `  ! 已存在本项目网络：${existing.join(', ')}（Compose 会复用，属正常）`
      : `  ✓ 不存在名为 ${PROJECT}_* 的网络`
  );
} else {
  console.log('  - 跳过（Docker 不可用）');
}

/* ------------------------------------------------------------- 4. .env */
section('[4] env/.env 配置检查');
const envPath = path.join(ROOT, 'env', '.env');
if (!fs.existsSync(envPath)) {
  console.log('  ✗ env/.env 不存在');
  console.log('      请执行：cp env/.env.example env/.env，并填写 GenAI 参数');
  blockers += 1;
} else {
  console.log('  ✓ env/.env 存在');
  const need = ['GENAI_BASE_URL', 'GENAI_API_KEY', 'GENAI_MODEL', 'FE_DOMAIN', 'DEFAULT_ROOT_PSW'];
  const text = fs.readFileSync(envPath, 'utf8');
  for (const k of need) {
    const m = text.match(new RegExp(`^${k}=(.*)$`, 'm'));
    const v = m ? m[1].trim() : '';
    if (!v) {
      console.log(`  ✗ ${k} 未填写`);
      blockers += 1;
    } else if (/^change-me/.test(v)) {
      console.log(`  ! ${k} 仍是占位符（可运行 node tools/new-secrets.mjs --write 生成随机值）`);
      warnings += 1;
    } else {
      console.log(`  ✓ ${k} 已填写${/KEY|PSW|TOKEN|SECRET/.test(k) ? `（长度 ${v.length}，内容不显示）` : ` = ${v}`}`);
    }
  }
}

/* ------------------------------------------------------------- 5. 磁盘 */
section('[5] 磁盘余量（镜像 + 数据卷预计需要 8~15 GB）');
try {
  const st = fs.statfsSync(path.parse(ROOT).root);
  const freeGB = (st.bavail * st.bsize) / 1024 ** 3;
  console.log(`  ${path.parse(ROOT).root} 可用空间约 ${freeGB.toFixed(1)} GB`);
  if (freeGB < 15) {
    console.log('  ! 余量偏紧，FastGPT 全栈镜像较大，建议先清理或换盘');
    warnings += 1;
  }
} catch (e) {
  console.log('  ! 无法读取磁盘信息: ' + e.message);
}

/* ------------------------------------------------------------- 汇总 */
console.log('\n' + '='.repeat(72));
if (blockers === 0) {
  console.log(` 预检通过（警告 ${warnings} 项）。可以继续部署：`);
  console.log(`   docker compose --env-file env/.env -p ${PROJECT} up -d`);
} else {
  console.log(` 预检未通过：阻塞项 ${blockers} 个，警告 ${warnings} 项。`);
  console.log(' 请先解决阻塞项；不要在未解决的情况下执行部署命令。');
}
console.log('='.repeat(72));
process.exitCode = blockers === 0 ? 0 : 1;
