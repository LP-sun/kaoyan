# 验收位置指南

这份文件回答一个问题：**我要看什么，去哪儿看？**

按“先看结论、再看证据、最后自己动手”的顺序排列。

---

## 一、先看结论（3 分钟）

| 想看什么 | 文件 |
| --- | --- |
| 全部验收结果总览 | [`docs/TEST_REPORT.md`](TEST_REPORT.md) 第 1 节表格 |
| 改过哪些位置 | 上面第 3 节（缺陷表）与第 6 节（浏览器检查） |
| 有哪些**没做到** | 上面第 10 节（已知未覆盖）、第 11 节（结论边界） |
| 项目结构 | [`../README.md`](../README.md) |
| 架构与设计取舍 | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| 判分算法边界 | [`DIAGNOSIS_ALGORITHM.md`](DIAGNOSIS_ALGORITHM.md) |
| 题库内容校验方式 | [`CONTENT_VALIDATION.md`](CONTENT_VALIDATION.md) |

**建议先读 `TEST_REPORT.md` 的第 10、11 节。** 那里写的是这份系统**不能**证明什么，
比“全部通过”更值得看。

---

## 二、看界面截图（10 分钟）

截图都是真实浏览器渲染的，不是设计稿。

### 主流程（`data/ui-check/`，13 张）

| 文件 | 内容 |
| --- | --- |
| `01-dashboard.png` | 学习总览（全新库，无作答） |
| `02-question.png` | 答题页（题卡 + 公式 + 作答控件） |
| `03-feedback.png` | 提交后的判分反馈 |
| `04-solution.png` | 展开的解析与标准答案 |
| `05-report.png` | 本轮诊断报告 |
| `06-knowledge-tree.png` | 知识树 |
| `07-wrong-answers.png` | 错题与复习 |
| `08-settings.png` | 设置与备份 |
| `09-narrow-quiz.png` | **窄屏 390px** 下的答题页 |
| `10-dashboard-after.png` | 作答后刷新（图表出现柱子） |
| `11-settings-online.png` | **在线模式 + 降级链展示** |
| `12-connection-result.png` | **连接测试结果（真实模型）** |
| `pixel-dashboard.png` | 像素检查用的总览图 |

旁边还有两份机器可读报告：`visual-report.json`（25 项 DOM 断言）、
`pixel-report.json`（6 项像素统计）。

### 进程级重启（`data/e2e-check/`，3 张）

`e2e-01-after-answer.png` → `e2e-02-after-restart.png` → `e2e-03-dashboard-final.png`。
这条链证明：**杀掉服务再启动，学习记录还在**。

### 真实在线模式（`data/e2e-online/`，2 张）

`online-connection.png`（连接成功）、`online-ai-answer.png`（真实模型回答）。

### 视觉模型评审记录（`data/vision-review/`）

| 文件 | 内容 |
| --- | --- |
| `vision-review.md` | 具备图像能力的模型（`GLM-4.6V`）对每张截图的**原始描述** |
| `vision-review.json` | 同上，机器可读 |
| `spotcheck.json` | 图表是否空坐标轴、窄屏是否溢出的定向回答 |

**这些是模型的原始观察，没有经过我的润色**，所以能看到它的判断（也能看到它的笔误）。

---

## 三、自己动手跑起来（最推荐的验收）

```powershell
cd PhysicsPrep

# 1) 启动（默认读 .env；本机 .env 已配好两套凭据）
.\.venv\Scripts\python.exe app.py
```

浏览器打开 **http://127.0.0.1:7860**（默认端口，`PHYSICSPREP_PORT` 可改）。
只监听 127.0.0.1，不产生分享链接。

> **注意区分两类实例**：直接 `python app.py` 启动的是正式实例，
> 学习记录写入 `data/physics_prep.sqlite3`（长期保留）。
> 此前文档与检查脚本用的 7861 是**一次性视觉检查实例**（`PHYSICSPREP_DB_PATH`
> 指向 `data/ui-check/study.sqlite3`，随时会被检查脚本重建），不要把正式学习
> 记录留在那个库里。若曾在检查实例里作答，可用
> `python tools/migrate_records.py --source data/ui-check/study.sqlite3 --target data/physics_prep.sqlite3`
> 迁移（主键冲突自动跳过）。

**值得亲手点的地方：**

1. **设置与备份** → 看「当前模式」与「降级顺序」→ 点「测试模型连接」
   应出现 `连接成功（在线模型） · 实际使用：DeepSeek-V4-Flash`。
2. **开始诊断** → 做一道题 → 看判分反馈与解析。
   回答框里试试 `sqrt(2*g*h)` 这类表达式（提示：乘号要显式写）。
3. **向 AI 教师提问**（折叠面板里）→ 问「这题用哪个守恒定律」。
   作答前后各问一次：**作答前提问不会直给最终答案**。
4. **学习总览** → 看图表柱子 → 点「刷新学习总览」。
5. **知识树 / 错题与复习 / 题库管理** → 各点一遍。
6. 把窗口拖窄到手机宽度，看是否出现横向滚动条。

### 想自己跑测试

```powershell
# 全部单元与集成测试（133 项）
.\.venv\Scripts\python.exe -m pytest -q

# 交付前自检（密钥 / 知识树 / 端到端冒烟 / 零告警）
.\.venv\Scripts\python.exe tools\preflight_check.py

# 浏览器交互检查（25 项）与像素检查（6 项）
# 它们会重建 data\ui-check 下的临时库，应针对单独启动的检查实例跑，不要用正式库：
#   $env:PHYSICSPREP_PORT='7861'; $env:PHYSICSPREP_DB_PATH='data\ui-check\study.sqlite3'
#   .\.venv\Scripts\python.exe app.py   （另开一个终端）
.\.venv\Scripts\python.exe tools\ui_visual_check.py http://127.0.0.1:7861 data\ui-check
.\.venv\Scripts\python.exe tools\check_render_pixels.py http://127.0.0.1:7861 data\ui-check

# 真实在线验收（16 项，读 .env 的真实凭据）
.\.venv\Scripts\python.exe tools\e2e_online_school_check.py

# 验证模型降级真的生效（故意损坏主模型）
.\.venv\Scripts\python.exe tools\e2e_online_school_check.py --break-primary

# 进程级重启验收（14 项，自己管理服务进程）
.\.venv\Scripts\python.exe tools\e2e_restart_check.py
```

> 注意：`e2e_online_school_check.py` 会**临时**改写 `.env`，结束时按原内容还原。
> 并发多跑会撞上游限流（实测遇到过 `RateLimitError`），串行跑更稳。

---

## 四、模型降级功能怎么看

**最快的一条命令**（真实网络、真实凭据、把主模型换成不存在的 ID）：

```powershell
.\.venv\Scripts\python.exe tools\e2e_online_school_check.py --break-primary
```

期望在输出里看到：

```
模型：definitely-not-a-real-model-xyz   ← 故意损坏（原本 DeepSeek-V4-Flash），期望降级到 DeepSeek-V4.1-Flash
降级链：definitely-not-a-real-model-xyz → DeepSeek-V4.1-Flash → Kimi-K2.6 → Qwen3.8-Flash
PASS  主模型不可用时已降级到备用模型 :: 连接成功（在线模型） · 实际使用：DeepSeek-V4.1-Flash
```

**看代码**：`physics_prep/llm/client.py` 的 `_hard_stop` / `_worth_switching_model`
两个函数就是全部策略；`Settings.models`（`physics_prep/config.py`）负责解析模型链。

**看测试**：`tests/test_model_fallback.py`（16 项），覆盖
主模型 404 → 降级、空内容 → 降级、限流 → 先重试再降级、
连接错误/超时 → 重试但**不**降级、401 → 立刻回退不重试。

---

## 五、凭据在哪里

| 组 | 位置 | 端点 | 模型 |
| --- | --- | --- | --- |
| A（`.env` 中生效） | `PhysicsPrep/.env` | `https://llmapi.paratera.com/v1` | `DeepSeek-V4-Flash` + 3 个备用 |
| B（`.env` 中注释备用） | `PhysicsPrep/.env` | `https://genaiapi.shanghaitech.edu.cn/api/v1/start` | `deepseek-v4-pro` |

- `.env` **已被 `.gitignore` 排除**（`.env` 与 `.env.*` 两条规则都验证过）；
- 旧的 `.env` 会被 `tools/setup_env_from_sources.py` 备份成 `.env.bak`（同样被排除）；
- `.env.example` 只有空值模板，**可以**提交；
- 切换 A/B 两组：把 A 组几行注释掉、把 B 组取消注释，重启 `app.py`。

> ⚠ `.env` 里有真实密钥。不要外发、不要贴进聊天记录、不要提交。
