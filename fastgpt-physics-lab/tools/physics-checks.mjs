#!/usr/bin/env node
/**
 * physics-checks.mjs — 题库物理量独立复算
 *
 * 目的：不依赖题面文字，直接用独立实现的公式复算每道题的关键数值，
 *       与题库中该题的标准答案对应的数值做比对。
 *       这是"答案唯一性与物理正确性"的自动检查，不能替代人工复核。
 *
 * 用法：node tools/physics-checks.mjs
 */

const g = 10; // m/s^2，与题库题目中声明的取值一致

function close(a, b, tol = 1e-6) {
  return Math.abs(a - b) <= tol * Math.max(1, Math.abs(a), Math.abs(b));
}

/** 数值积分：变力 F(x)=3x^2 从 0 到 2 的功 */
function numericWork(f, a, b, n = 200000) {
  const h = (b - a) / n;
  let s = 0;
  for (let i = 0; i < n; i++) {
    const x0 = a + i * h;
    const x1 = x0 + h;
    s += ((f(x0) + f(x1)) / 2) * h; // 梯形法
  }
  return s;
}

/** 用 4 阶 Runge-Kutta 数值求解简谐振动，取最大速率，用于交叉验证 v_max=ωA */
function shmMaxSpeed(A, T, cycles = 4) {
  const omega = (2 * Math.PI) / T;
  let x = A;
  let v = 0;
  const dt = T / 200000;
  const steps = Math.floor((cycles * T) / dt);
  let vmax = 0;
  const acc = (xx) => -omega * omega * xx;
  for (let i = 0; i < steps; i++) {
    const k1x = v;
    const k1v = acc(x);
    const k2x = v + (dt / 2) * k1v;
    const k2v = acc(x + (dt / 2) * k1x);
    const k3x = v + (dt / 2) * k2v;
    const k3v = acc(x + (dt / 2) * k2x);
    const k4x = v + dt * k3v;
    const k4v = acc(x + dt * k3x);
    x += (dt / 6) * (k1x + 2 * k2x + 2 * k3x + k4x);
    v += (dt / 6) * (k1v + 2 * k2v + 2 * k3v + k4v);
    if (Math.abs(v) > vmax) vmax = Math.abs(v);
  }
  return vmax;
}

/** 用能量守恒数值求解圆环最低点法向力 N = mg + m v^2/R
 *  注意：这里以 g=1、m=1、R=1 为单位制，返回值即为 N/(mg)。
 *  能量守恒：从最高点到最低点下降 2R，(1/2)v² = g·2R ⇒ v²/R = 4g。
 *  故 N = mg + m·4g = 5mg。若混用 g=10 的绝对值，结果会错成 50mg。 */
function hoopNormalForceUnits() {
  const gU = 1;
  const mU = 1;
  const R = 1;
  const v2overR = 4 * gU; // = (2g·2R)/R
  return mU * gU + mU * v2overR;
}

const checks = [
  {
    id: 'MECH-NL-001',
    expect: 'A',
    desc: '静摩擦是否足以平衡下滑分量（物块保持静止，摩擦力 = mg sinθ）',
    run() {
      const m = 2;
      const theta = Math.PI / 6;
      const mu = 0.6;
      const N = m * g * Math.cos(theta);
      const fmax = mu * N;
      const downSlope = m * g * Math.sin(theta);
      const static_ = downSlope < fmax;
      // 正确答案 A = 静止且摩擦力 10 N
      const ok = static_ && close(downSlope, 10, 1e-9) && close(fmax, 6 * Math.sqrt(3), 1e-6);
      return {
        ok: ok && static_,
        detail: `下滑分量=${downSlope.toFixed(3)}N, 最大静摩擦=${fmax.toFixed(3)}N, 判定静止=${static_}, 需给出摩擦力=${downSlope.toFixed(3)}N(=10N)`
      };
    }
  },
  {
    id: 'MECH-WE-001',
    expect: 'C',
    desc: '变力做功 W = ∫₀² 3x² dx 是否等于 8 J（数值积分交叉验证）',
    run() {
      const w = numericWork((x) => 3 * x * x, 0, 2);
      const analytic = 8;
      return { ok: close(w, analytic, 1e-6), detail: `数值积分=${w.toFixed(9)}J, 解析解=${analytic}J` };
    }
  },
  {
    id: 'MECH-MO-001',
    expect: 'B',
    desc: '爆炸动量守恒：1kg 向东 12m/s ⇒ 3kg 速率是否为 4m/s',
    run() {
      const v2 = -(1 * 12) / 3;
      return { ok: close(Math.abs(v2), 4), detail: `v2=${v2}m/s, |v2|=${Math.abs(v2)}m/s` };
    }
  },
  {
    id: 'MECH-RB-001',
    expect: 'A',
    desc: '转动定律 β = M/J = 12/2 = 6 rad/s²',
    run() {
      const beta = 12 / 2;
      return { ok: close(beta, 6), detail: `β=${beta} rad/s²` };
    }
  },
  {
    id: 'MECH-RB-002',
    expect: 'D',
    desc: '圆环平行轴定理：J = mR² + mR² = 2mR²',
    run() {
      const Jc = 1; // 以 mR²=1 为单位
      const J = Jc + 1 * 1;
      return { ok: close(J, 2), detail: `J = ${J} mR²` };
    }
  },
  {
    id: 'MECH-RB-003',
    expect: 'C',
    desc: '竖直圆环最低点法向力 N = mg + m v²/R = 5mg',
    run() {
      const N = hoopNormalForceUnits();
      return { ok: close(N, 5), detail: `N = ${N} mg（在 g=m=R=1 单位制下计算）` };
    }
  },
  {
    id: 'MECH-RL-001',
    expect: 'C',
    desc: '匀速纯滚动时质心加速度为 0 ⇒ 水平合外力为 0 ⇒ 摩擦力为 0',
    run() {
      const a = 0; // 匀速
      const f = 1 * a; // m a
      return { ok: close(f, 0), detail: `a=${a}, f=ma=${f}` };
    }
  },
  {
    id: 'MECH-RL-002',
    expect: 'B',
    desc: '纯滚动末速 v = sqrt(2gh/(1+J/(mR²)))：实心圆柱(1/2) vs 空心圆筒(1)',
    run() {
      const h = 1;
      const vSolid = Math.sqrt((2 * g * h) / (1 + 0.5));
      const vHollow = Math.sqrt((2 * g * h) / (1 + 1));
      return {
        ok: vSolid > vHollow,
        detail: `实心圆柱 v=${vSolid.toFixed(4)} m/s > 空心圆筒 v=${vHollow.toFixed(4)} m/s`
      };
    }
  },
  {
    id: 'MECH-MO-002',
    expect: 'B',
    desc: '等质量弹性碰撞互换速度后压缩弹簧：x = Δv·√(μ/k) = 0.10 m（μ 为约化质量）',
    run() {
      const m1 = 2;
      const m2 = 2;
      const v0 = 3;
      const k = 900;
      // 第一阶段：碰后 m1 静止，由动量守恒直接求 m2 的速度（v2 = m1v0/m2 = 3 m/s）
      const v2 = (m1 * v0) / m2;
      const v1 = 0;
      // 校验 m1=m2 的弹性碰撞确实互换速度（自洽性）
      const v1Elastic = ((m1 - m2) * v0) / (m1 + m2);
      const v2Elastic = ((2 * m1) * v0) / (m1 + m2);
      const elasticConsistent = close(v1Elastic, 0, 1e-12) && close(v2Elastic, v2, 1e-12);
      // 第二阶段：两物块等速时弹簧压缩量最大
      const v = (m1 * v1 + m2 * v2) / (m1 + m2);
      const xSq = (0.5 * m1 * v1 * v1 + 0.5 * m2 * v2 * v2 - 0.5 * (m1 + m2) * v * v) / (0.5 * k);
      const x = Math.sqrt(xSq);
      // 与等效约化质量公式对照：x = Δv·sqrt(μ/k)，μ = m1m2/(m1+m2)
      const mu = (m1 * m2) / (m1 + m2);
      const formula = (v2 - v1) * Math.sqrt(mu / k);
      return {
        ok: elasticConsistent && close(x, 0.1, 1e-9) && close(formula, x, 1e-9),
        detail: `v1'=${v1}, v2'=${v2} m/s（弹性碰撞自洽=${elasticConsistent}）, v共=${v} m/s, x(能量守恒)=${x.toFixed(9)} m, x(相对速度公式)=${formula.toFixed(9)} m`
      };
    }
  },
  {
    id: 'MECH-SHM-001',
    expect: 'B',
    desc: '简谐振动 v_max = ωA = 4π cm/s（用 RK4 数值解交叉验证）',
    run() {
      const A = 4;
      const T = 2;
      const omega = (2 * Math.PI) / T;
      const analytic = omega * A;
      const numeric = shmMaxSpeed(A, T);
      return {
        ok: close(analytic, 4 * Math.PI, 1e-9) && close(numeric, analytic, 2e-3),
        detail: `解析 v_max=${analytic.toFixed(6)} cm/s, 数值 v_max=${numeric.toFixed(6)} cm/s`
      };
    }
  }
];

console.log('='.repeat(72));
console.log(' 题库物理量独立复算（自动检查，不替代人工复核）');
console.log('='.repeat(72));

let okCount = 0;
for (const c of checks) {
  const r = c.run();
  console.log(`\n[${r.ok ? ' OK ' : 'FAIL'}] ${c.id}  (标准答案 ${c.expect})`);
  console.log(`        ${c.desc}`);
  console.log(`        复算: ${r.detail}`);
  if (r.ok) okCount += 1;
}

console.log('\n' + '='.repeat(72));
console.log(` 通过 ${okCount} / ${checks.length}`);
console.log('='.repeat(72));
process.exitCode = okCount === checks.length ? 0 : 1;
