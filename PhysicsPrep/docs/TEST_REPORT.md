# 测试报告

生成时间：本次交付验证运行。全部命令在项目根目录 `PhysicsPrep/` 下执行。

## 1. 结果概览

| 项目 | 结果 |
| --- | --- |
| 自动化测试 | **133 passed, 0 failed, 0 errors**（9 个文件，JUnit XML 计数） |
| 运行耗时 | 约 37 秒 |
| 浏览器视觉/交互检查 | **25 / 25 通过**（Playwright + Chromium，真实渲染） |
| **视觉模型看图验收** | **10 张截图逐张描述 + 3 项定向复核 + 2 张设置页复核**（`GLM-4.6V`，见第 6.4 节） |
| 像素级渲染检查 | **6 / 6 通过**（PIL 墨水量 + DOM 尺寸） |
| 真实进程级端到端 | **14 / 14 通过**（答题 → 杀掉服务 → 重启 → 记录仍在） |
| 在线配置启动与回退 | **11 / 11 通过**（真实 `.env` + 真实启动 + 浏览器） |
| **学校 GenAI 真实端点** | **16 / 16 通过**（真实凭据、真实网络、真实模型回答） |
| **Paratera 端点 + 模型降级** | **16 / 16 通过**（主模型故意损坏 → 降级到备用模型接手） |
| 交付前自检 | **全部通过**（密钥扫描 / 知识树 / 端到端冒烟 / 自身零告警） |
| GenAI 在线代码路径 | 已用真实 `OfficialGenAIClient` + Mock 传输层覆盖（15 项） |
| 模型降级逻辑 | **16 项单元测试**（`tests/test_model_fallback.py`） |
| Mock 模式 | 全流程通过，无需网络 |

### 测试文件分布

| 文件 | 用例数 | 覆盖内容 |
| --- | ---: | --- |
| `test_backend.py` | 8 | 迁移幂等、外键、WAL、快照与幂等提交、持久化、导入导出与循环检测、备份恢复、AI 题审核门、选题补救 |
| `test_math_llm.py` | 13 | 选择/多选判分、符号等价、非法表达式、数值容差、超时、Mock 客户端、超时回退、在线成功响应 |
| `test_seed_grading.py` | 41 | 30 道种子题标准答案自判、简答不冒充机器判分、等价变形、8 类攻击输入、零值与复数常量（文件内仅 6 个测试函数，41 = 6 个函数 + 29 个按客观题参数化的用例 + 8 个攻击输入参数化用例；按题目条目计为 25） |
| `test_online_mode.py` | 15 | 合法 GenAI 配置下的客户端与**界面事件处理器**接线、重试、回退、Mock 切换、密钥不回显、返回契约 |
| `test_ui.py` | 3 | 题卡不携带答案状态、切题清空输入、反馈与空数据看板 |
| `test_ui_views.py` | 22 | 知识树/错题本/设置脱敏/提示词/单位/客户端边界/反馈文案 |
| `test_acceptance.py` | 8 | 场景 A/B/C 端到端、四类题型闭环、Mock 全流程 |
| `test_selector_types.py` | 7 | 自适应诊断只派发可确定性判分题型；开放题仅在候选池只剩它时兜底；符号报错列出可用符号 |
| **合计** | **117** | 本表已含 `test_model_fallback.py` 的 16 项（见上表“模型降级逻辑”行）。与 `pytest --collect-only` 采集的 **133** 相差 16 项，全部来自 `test_seed_grading.py` 的参数化：该文件按采集计 41 项、按题目条目计 25 项，本表采用条目口径 |

## 2. 运行方式

```bash
# 在项目根目录
.venv/Scripts/python.exe -m pytest                          # 全部测试
.venv/Scripts/python.exe -m pytest -v                       # 详细输出
.venv/Scripts/python.exe -m pytest tests/test_acceptance.py # 只跑验收场景
.venv/Scripts/python.exe tools/count_tests.py               # 统计用例数
.venv/Scripts/python.exe tools/preflight_check.py           # 交付前自检
.venv/Scripts/python.exe tools/e2e_restart_check.py         # 真实进程级重启验收
```

正确性以 JUnit XML 为准（终端摘要行在部分环境下会被吞掉）：

```bash
.venv/Scripts/python.exe -m pytest --junitxml=report.xml
# tests=107 failures=0 errors=0 skipped=0
```

### 关于测试临时目录

`test_backend.py`、`test_acceptance.py`、`test_ui_views.py`、`test_online_mode.py` 使用 pytest 的 `tmp_path`。
在受限沙箱环境中，相关用例会以 **error**（而非 failure）出现，报
`PermissionError: [WinError 5] 拒绝访问`。这是环境权限问题，不是代码缺陷：
在正常用户环境下（本次已验证）133 个用例全部通过。

**根因（2026-10-10 实测定位）**：报错发生在 `shutil.rmtree(path)` → `os.rmdir(path)`，
即 pytest 能**创建并写入**临时目录，却在清理阶段**无法删除**它。
因此**不要**指望 `--basetemp=<工作区内目录>` 能解决——该方案是错的，实测无效：
把 basetemp 指到工作区内的 `.pytest_tmp` 后仍然失败，失败点仍是删除该目录本身。
工作区里遗留的 `.pytest_tmp`、`.test_core`、`.test_core2`、`.test_progress`、
`.test_progress2` 就是这一机制的产物：它们能建出来，但删不掉。

沙箱下真正可行的做法是**让 pytest 不清理**，而不是换个可写位置：

```bash
# 关掉 tmp_path 的自动清理（保留目录，避开 rmdir）
.venv/Scripts/python.exe -m pytest -p no:cacheprovider --basetemp=.pytest_tmp
# 说明：上面这条在工作区沙箱下仍会因 rmdir 失败而报错，
# 只是能把失败原因稳定暴露在清理阶段；要完整跑通需在没有
# 目录删除限制的普通用户终端中执行。
```

### 关于警告策略

`pyproject.toml` **不再**把弃用警告升级为失败。原因：Gradio 5.x 在构造组件时会发出多条
Gradio 6.0 迁移提示（`theme`/`css` 参数、`gr.HTML` 的 `padding` 默认值、`row_count` 元组等），
逐条 `ignore` 既脆弱又会掩盖新出现的提示。

真正要守住的约束改由 `tools/preflight_check.py` 承担：构造整个界面时用
`warnings.catch_warnings(record=True)` 抓取全部告警，按 message 文本区分
“已知上游迁移提示”与“本项目代码告警”，后者一条都不允许。
该检查已用故意插入的 `warnings.warn('probe-own-warning')` 验证过确实会失败，
不是空转的检查。

## 3. 本次修复的缺陷

| # | 缺陷 | 影响 | 处理 |
| --- | --- | --- | --- |
| 1 | `math_grader` 依赖 `multiprocessing` 子进程做超时 | **判分完全不可用**：命名管道被禁止的环境中每次判分都抛 `PermissionError`，46 个用例失败 | 重写为纯进程内实现 + 墙钟截止时间检查；判分恢复且不再依赖子进程 |
| 2 | 判分对浮点答案过严 | `1.00000001` vs `1` 在符号题中被判 `incorrect` | 差异含浮点数时按容差比较 |
| 3 | `dashboard()` 混用 aware / naive datetime | 一旦存在答题记录，`today_count` 比较抛 `TypeError` | 统一改用 `physics_prep/clock.py` 的 UTC 辅助函数 |
| 4 | `datetime.utcnow()` 在 3.12 弃用 | 20 条 DeprecationWarning | 全部改为 `clock.naive_utcnow()` / `clock.utcnow()` |
| 5 | `settings.mask_key` 对短密钥回显完整内容 | 4 字符以内的密钥等于明文显示 | 短于 12 字符只报告长度 |
| 6 | 复合单位（`m/s`）无法识别 | 单位提示失效 | 增加复合单位整体识别；仍保持“只提示不判错” |
| 7 | 迁移只有硬编码版本 1，无可重复机制 | 无法演进表结构 | 新增版本化 `MIGRATIONS` 列表 + 幂等 runner |
| 8 | 图表在学生答题后停留在旧快照 | 用户看到 0 值图表，误以为功能坏了 | 浏览器检查已断言“点击刷新后柱子出现”；界面保留“刷新学习总览”按钮 |
| 9 | `safe()` 包装后所有事件处理器都叫 `wrapped` / `wrapped_23` | 无法按名字定位处理器，`/api` 文档与测试都只能靠猜序号 | `functools.wraps` + 显式名注册；新增测试断言关键处理器可按语义名找到 |
| 10 | `test_backend.py` 等用例在 `error::DeprecationWarning:physics_prep.*` 下被 Gradio 自身迁移提示打断 | 一旦测试构造真实界面就会误报失败 | 移除全局升级，改为 preflight 中“本项目代码零告警”的定向检查 |
| 11 | **在线失败时 `test_connection()` 返回 `mode='online'`，界面同时显示“连接成功（在线模型）”和一段回退内容** | 连通性判断被误导：用户会以为在线可用，实际看到的是替换文本 | 新增 `fallback_text` 标记并把 `mode` 语义写进返回契约；`connection_report` 在失败时不再展示替换内容，改为给出排查顺序 |


### 关于缺陷 1 的说明

原实现用 `ctx.Process` + `ctx.Queue` 把 SymPy 计算隔离到子进程并 `p.terminate()` 硬超时。
该设计在原理上更安全，但在当前运行环境中 **`multiprocessing` 的命名管道不可用**，
导致每次判分都抛异常并返回 `uncertain`——即整个平台的核心功能失效。

新实现改为：AST 白名单构造表达式（限制长度/节点数/深度/幂指数）→ 每步检查截止时间 →
不可判定时返回 `uncertain`。风险控制来自解析前的输入约束，而不是进程隔离。

代价：理论上存在“某个表达式在截止时间内无法被中断”的残余风险。缓解措施是
输入上限（300 字符 / 100 节点 / 深度 15 / 指数 ≤ 20 / 字面量 ≤ 1e12）与
`together → cancel → simplify` 的渐进式化简顺序。**这一点是已知取舍，如实记录。**

## 4. 端到端验收场景

| 场景 | 测试 | 断言要点 |
| --- | --- | --- |
| **A 正常诊断** | `test_scenario_a_normal_diagnosis` | 开始 → 拿题（不含答案）→ 答对 → 反馈含标准答案/解析/知识点/掌握度 → 下一题换题 → 报告 accuracy=1.0 |
| **A 扩展** | `test_scenario_a_covers_multiple_question_types` | 单选/多选/数值/符号四类题型标准答案均自判为 `correct` |
| **B 错误补救** | `test_scenario_b_error_remedy` | 纯滚动题答错 → `incorrect` → 进错题本（含快照）→ 掌握度 < 0.5 且次数=1 → 复习间隔 1 天 → 不再立刻重复同题 |
| **B 选题** | `test_scenario_b_selector_prefers_remedy_and_avoids_loop` | 答错后优先前置考点，理由含“补救/前置”；连续同考点后不再叠加 |
| **C 重启恢复** | `test_scenario_c_restart_recovery` | 释放连接并用新实例打开同一文件 → `resume()` 返回同一会话、错题一致、报告一致、掌握度逐项一致、题库不重复导入 |
| **C 续答** | `test_scenario_c_restart_continues_same_question` | 重启后继续上次学习回到未提交的那道题 |
| **Mock 全流程** | `test_mock_mode_full_flow_without_api_key` | 无任何密钥时判分/记录/诊断/AI 引导全部可用 |
| **Mock 标识** | `test_mock_client_never_claims_to_be_model_reasoning` | Mock 输出恒带“非模型推理”标记 |

## 5. 需求覆盖对照

| 需求条款 | 覆盖测试 |
| --- | --- |
| SQLite 初始化与迁移 | `test_backend.py::test_repeatable_migration_and_foreign_keys` |
| 题库导入 | `test_backend.py::test_import_export_atomic_and_cycles` |
| 单选题判分 | `test_math_llm.py::test_choices` |
| 数学表达式等价性 | `test_math_llm.py::test_symbolic`、`test_seed_grading.py::test_rolling_alternative_form_and_positive_domain` |
| 非法表达式处理 | `test_math_llm.py::test_unsafe`（7 例）、`test_seed_grading.py::test_untrusted_expression_syntax_returns_uncertain`（8 例） |
| 选题算法 | `test_backend.py::test_selector_remedy_coverage_and_no_loop` |
| 掌握度更新 | `test_backend.py::test_public_snapshot_and_idempotency`、`test_acceptance.py::test_scenario_b_error_remedy` |
| 错题记录 | `test_backend.py::test_error_remedy_and_persistence`、`test_ui_views.py::test_wrong_rows_and_history_after_incorrect` |
| 数据持久化 | `test_acceptance.py::test_scenario_c_restart_recovery` |
| 重复提交保护 | `test_backend.py::test_public_snapshot_and_idempotency`（token 复用返回同一反馈，`attempts` 仍为 1 行） |
| GenAI 超时与异常回退 | `test_math_llm.py::test_timeout_fallback`、`test_ui_views.py::test_online_client_never_echoes_api_key_on_failure` |
| Mock 模式完整流程 | `test_acceptance.py::test_mock_mode_full_flow_without_api_key` |

## 6. 浏览器检查（真实渲染）

脚本：`tools/ui_visual_check.py`（Playwright 驱动本机 Chromium，1440×1000 与 390×844 两种宽度）。

```bash
python app.py                                   # 一个终端
python tools/ui_visual_check.py http://127.0.0.1:7861 data/ui-check   # 另一个终端
python tools/check_render_pixels.py http://127.0.0.1:7861 data/ui-check
```

### 25 项检查全部通过

- 首页：标题、4 张统计卡
- 答题：科目下拉可选、题卡正文、元信息含题型/难度/选题理由、**KaTeX 已渲染（2 个公式节点）**
- **作答前页面上不存在“标准答案”“推导与检验”文本**
- 提交后：反馈出现、含关联知识点、含错因判断
- 解析：含标准答案与推导检验
- 下一题：反馈被清空、题干已更换
- 诊断报告、知识树四级结构、错题页、设置页显示模式说明
- **设置页不出现 `GENAI_API_KEY=`，不泄露完整密钥**
- 桌面与窄屏均无横向溢出（`scrollWidth == clientWidth`）
- **点击“刷新学习总览”后图表画出非零柱子，柱子数 = 7，统计卡更新**

### 像素级检查全部通过

| 检查 | 实测 |
| --- | --- |
| 图表容器高度 | 260 px（未被压扁） |
| 图表 SVG 已挂载 | 800×260 |
| 柱状图数据点 | 7 个 |
| 坐标轴刻度 | x=7, y=5 |
| 图表区域墨水比例 | 2.07%（非空白） |
| 内容居中 | 左 44 px / 右 44 px（容器 1280 px） |

### 截图产物

`data/ui-check/` 下有 10 张全页截图：

`01-dashboard` · `02-question` · `03-feedback` · `04-solution` · `05-report` ·
`06-knowledge-tree` · `07-wrong-answers` · `08-settings` · `09-narrow-quiz` · `10-dashboard-after`

另有 `visual-report.json`（25 项断言）与 `pixel-report.json`（像素指标）。

### 6.4 视觉模型看图验收（`tools/vision_review.py`）

第 6.1–6.3 节是 DOM 断言与像素统计。**它们都不能替代真正“看图”**：DOM 能证明元素存在，
像素能证明区域非空，但证明不了「看起来是否乱」。本项目的执行模型不支持图像输入，
所以这一步改由具备图像输入能力的模型完成。

使用 Paratera 通道的 **`GLM-4.6V`**，对 `data/ui-check/` 下 10 张真实截图逐张描述
（原始输出见 `data/vision-review/vision-review.md`）。

**一个必须记录的坑。** 首次运行时 4 张截图返回**空字符串**。原因不是模型不支持图像，
而是 `GLM-4.6V` 是推理型模型：它把 `max_tokens` 预算先花在内部推理上，
预算不足 1200 时 `content` 直接为空（实测 `reasoning_tokens` 约占 completion 的 40%）。
把预算提到 4000 后 10 张全部正常返回。**如果只看第一次结果，会得出“视觉验收失败”的错误结论。**

#### 模型确认的关键内容

| 项目 | 模型的观察 |
| --- | --- |
| 页面文字 | 逐字抄回了标题、导航、统计卡、按钮与提示文案，与实现一致 |
| **LaTeX 渲染** | 在解析页读到 `m > 0`、`0 < θ < π/2`、`sqrt(2*g*h)`、`g*sin(theta)`、`mg sinθ`、`ma = mg sinθ`、`a = g sinθ` |
| 结构 | 首页「统计卡片 4 个，图表 1 个」；知识树「表格 1 个」；错题页「表格 1 个」；设置页「输入框 4 个」 |
| 配色 | 深蓝导航 + 白色背景 + 浅蓝按钮，**文字对比足够，字号舒适** |
| 排版缺陷 | 10 张全部报告**无**文字溢出、元素重叠、乱码/豆腐块、加载失败、截断 |

模型抄录的文案与实现一致，说明它确实在读图而不是编造。但它也有抄录错误
（把知识树说明里的词读错、把设置页的「API Key」读成「密码」、误列了不存在的导航项
「首页总览」），因此**它的文字抄录只能当参考，精确文本以 DOM 断言为准**。

#### 6.4.1 定向复核：图表与窄屏（`tools/vision_spotcheck.py`）

总览式描述会漏细节（模型对图表只写了「图表 1 个」），所以对两个关键疑点单独提问。

**疑点 A：首页图表是不是空坐标轴？**（此前确实出现过这个问题）

| 截图 | 状态 | 模型的回答 |
| --- | --- | --- |
| `01-dashboard.png` | 全新数据库，尚无作答 | 「图表里**没有柱子**…**图表区域出现大片空白**」 |
| `10-dashboard-after.png` | 完成 1 题并刷新后 | 「图表里**有柱子**，1 根…**没有出现大片空白**」 |

这独立复现了第 3 节缺陷 8 的机制与修复：**没有数据时确实表现为空坐标轴，
有数据后柱子正常出现**。之前我基于像素统计判断“图表正常”，是因为当时数据库已有作答；
视觉复核把两个状态都看到了。

**疑点 B：窄屏（约 390px）是否有横向问题？** 模型回答 6 项全部为“否”：
无横向滚动条、无右边缘裁切、导航标签未换行或截断、题目/输入框/按钮完整无重叠、
表格未溢出、文字仍可读。

## 7. GenAI 在线连通性

### 7.1 真实端点：**已验证连通**

先前版本的报告中写着「环境未提供凭据，无法验证」。**这个结论是错的**，
原因是我只在项目目录里找凭据，没有检查运行环境自身的配置。
实际情况：

| 来源 | 内容 |
| --- | --- |
| DSH 配置 `llm-deepseek.baseURL` | `https://genaiapi.shanghaitech.edu.cn/api/v1/start` |
| DSH 凭据库 | `DEEPSEEK_API_KEY`（32 字符）已配置 |
| 探测结果 | `/api/v1/start/chat/completions` → **HTTP 200**，真实 vLLM 推理响应 |
| 可用模型 | `deepseek-v4-pro`、`DeepSeek-V4-Pro`（服务端实际模型名 `deepseek-pro`） |
| 无权限模型 | `deepseek-chat` → 403「该模型无使用权限」 |
| 不存在的模型 | `DeepSeek-V3.2` → 404「未找到模型节点」 |

关键结论：**项目原有的 Base URL 约定是正确的** —— `.env` 里 `GENAI_BASE_URL` 填到
`/api/v1/start`，OpenAI SDK 会自动补 `/chat/completions`，与学校端点匹配，
客户端代码无需改动。

> 说明：以上凭据来自运行环境自身（DSH 本机配置），不是项目的一部分。
> 项目仓库里**没有** `.env`，也没有任何密钥。本报告不记录密钥值。

### 7.2 真实在线端到端验收（`tools/e2e_online_school_check.py`，16 项）

用**真实凭据 + 真实网络 + 真实模型**跑完整流程。脚本把凭据写入临时 `.env`，
结束时删除（原文件存在则还原），并断言服务日志里不出现密钥。

脚本支持两套凭据来源，**两套都实测通过**：

| 来源 | 端点 | 模型 | 结果 |
| --- | --- | --- | --- |
| DSH 本机凭据库 `DEEPSEEK_API_KEY` | `genaiapi.shanghaitech.edu.cn/api/v1/start` | `deepseek-v4-pro` | 16/16 通过 |
| 同工作区 `fastgpt-physics-lab/env/.env` 的 `GENAI_*`（`--env-file` 借用） | `llmapi.paratera.com/v1` | `DeepSeek-V4-Flash` | 16/16 通过 |

| 检查 | 实测 |
| --- | --- |
| 写入临时 `.env`（真实在线配置） | 已写入 |
| 服务以真实在线配置启动成功 | HTTP 200 |
| 设置页报告 GenAI 在线模式 | `当前模式：GenAI 在线` |
| 设置页显示配置的端点主机 | 与配置一致 |
| 设置页显示模型 ID | 与配置一致 |
| **设置页不回显密钥** | 密钥未出现在页面文本中 |
| **「测试模型连接」真的连通** | `连接成功（在线模型） 连接成功` |
| 未回退 Mock | 报告中不含「已回退 Mock」 |
| 已取到题目 | `PHY-000021` |
| **AI 教师作答前提问得到真实模型输出** | 学校端点：**「动量守恒定律。」**；Paratera：**「无法唯一确定；请先提供题干或系统条件…」** |
| 回答不是 Mock 模板 | 不含 `【Mock 教师，非模型推理】` |
| 未发生在线回退 | 不含「已回退离线引导」 |
| **服务日志未泄露密钥** | 是 |
| `.env` 已还原为无密钥状态 | 已删除 |

截图：`data/e2e-online/online-connection.png`、`online-ai-answer.png`。

#### 两个实测教训

**（1）固定 sleep 会制造假失败。** 真实模型首次响应可能超过 30 秒（冷启动）。
验收脚本原先用固定 `sleep 30` 等待，导致一次假失败（页面仍显示 `processing`）。
已改为轮询到结果真的出现。

**（2）限流会发生，而平台的处理是对的。** Paratera 那套凭据在首次运行时出现
`RateLimitError` ——原因是当时我**并发**跑了视觉模型调用与多个验收脚本，
用的是同一个 key。平台的表现完全正确：捕获异常、**回退 Mock、界面保持可用**，
并按设计报告了「在线调用失败（RateLimitError），已回退离线引导」。
停掉并发、稍等片刻后重跑即 16/16 通过。
这说明 7.5 节的回退路径不是纸面设计，而是在真实限流下被实际触发并验证过的。

### 7.3 在线代码路径：Mock 传输层覆盖（15 项，`tests/test_online_mode.py`）

用 `httpx.MockTransport` 替换**网络传输层**，其余全部走真实实现
（真实的 `Settings`、真实的 `create_client`、真实的 `OfficialGenAIClient.ask()`、
真实的界面事件处理器）。唯一被替换的是字节怎么过网线。

| 检查 | 断言要点 |
| --- | --- |
| 合法配置建出在线客户端 | `isinstance(client, OfficialGenAIClient)`，`name == 'genai'` |
| 请求结构正确 | 发到配置的地址，`model` 为配置的模型 ID，消息为 `['system','user']` |
| 连接测试 | 返回“连接成功（在线模型）”，`error is None` |
| 连接失败回退 | `mode == 'mock'`，保留异常类别，重试 3 次（1 + 2） |
| 重试后成功 | 前两次超时、第三次成功 → `mode == 'online'` |
| **界面设置页显示在线成功** | 调 `connection` 处理器 → 含“连接成功（在线模型）”，且不含密钥 |
| **界面设置页显示回退** | 含“已回退 Mock”与异常类别，且不含密钥 |
| **AI 教师作答前** | system 提示含“不要公布最终答案” |
| **AI 教师提交后** | system 提示不再含该禁令 |
| **用户索取完整解析** | system 提示切到完整解析模式 |
| 应用运行期配置 | `configure()` 生效于运行期配置单元，返回在线模式摘要 |
| 切到 Mock 后不再联网 | 切换后 `connection()` 报告 Mock，且网络调用计数为 0 |

### 7.4 界面如何区分三种状态

无论哪种情况，界面都不会把 Mock 伪装成在线，只会给出这三种结论之一：

- `连接成功（在线模型）`
- `在线调用失败，已回退 Mock · 原因类别：<异常类名>`
- `当前为 Mock 模式（未发起在线请求）`

### 7.5 在线但端点不可达时的行为（`tools/e2e_env_fallback_check.py`）

7.2 证明的是「能连上」；这一节证明的是「**连不上时不崩**」。用**格式合法但不可达**的
HTTPS 地址写真实 `.env`、真实执行 `app.py`、在浏览器里观察。

> 补充：这条回退路径后来在 7.2 的 Paratera 限流场景中被**真实触发**过一次
> （`RateLimitError`），界面表现与本节的预测一致 —— 不是只在构造场景里成立。

| 检查 | 实测 |
| --- | --- |
| 写入临时 `.env`（含在线配置） | 已写入 |
| 服务以在线配置启动成功 | HTTP 200 |
| 首页正常渲染 | ≥4 张统计卡 |
| 设置页报告为 **GenAI 在线** 模式 | 是 |
| 设置页显示配置的模型 ID | `e2e-placeholder-model` |
| **设置页不回显 API Key** | 占位密钥未出现在页面文本中 |
| **连接失败后明确报告已回退 Mock** | `在线调用失败，已回退 Mock · 原因类别：APIConnectionError` |
| 报告了失败原因类别 | `APIConnectionError` |
| **未把 Mock 伪装成在线成功** | 不出现“连接成功（在线模型）” |
| 在线失败时仍可开始诊断 | 题卡正常出现 |
| `.env` 已还原为原状 | 已还原 |

### 7.6 模型降级链的真实端到端验证（`--break-primary`）

前面几节验证的是「配好了就能用」。这一节验证的是「**主模型坏了会怎样**」。

做法：读取项目 `.env` 的真实凭据，只把 `GENAI_MODEL` 换成
`definitely-not-a-real-model-xyz`，`GENAI_MODEL_FALLBACKS` 保持原样，
然后跑完整浏览器验收。

```
模型：definitely-not-a-real-model-xyz   ← 故意损坏（原本 DeepSeek-V4-Flash），期望降级到 DeepSeek-V4.1-Flash
降级链：definitely-not-a-real-model-xyz → DeepSeek-V4.1-Flash → Kimi-K2.6 → Qwen3.8-Flash
```

界面上实际出现的结果：

> **连接成功（在线模型） · 实际使用：`DeepSeek-V4.1-Flash`**
> （`definitely-not-a-real-model-xyz` 不可用，已降级到 `DeepSeek-V4.1-Flash`）

| 检查 | 实测 |
| --- | --- |
| 设置页显示降级顺序 | 4 个模型全部列出 |
| **主模型不可用时已降级到备用模型** | 实际使用 `DeepSeek-V4.1-Flash` |
| **报告了不可用的主模型** | 页面点名 `definitely-not-a-real-model-xyz` |
| AI 教师提问得到真实模型输出 | 是（来自降级后的模型） |
| 未发生在线回退 | 是（没有掉到 Mock） |

对照实验：不损坏主模型时，同样的验收报告「实际使用：`DeepSeek-V4-Flash`」，
**没有**降级 —— 说明降级只在真的需要时才发生，不是无条件轮换。

这个方法（故意配坏主模型）是可复用的：任何声称有降级能力的系统都应该能通过
这个测试；通不过就说明降级只是文档里的一句话。

### 7.7 交付前自检里 `.env` 检查的修正

原来有一条检查是 `.env 未被提交`，实现却是「`.env` 文件不存在」。
这在没有凭据时能通过、一旦配上真实凭据就必然失败 —— 它把「文件存在」当成了「会被提交」，
是**假检查**。已改为真正验证 gitignore 规则（用 `fnmatch` 判断 `.env`、`.env.local`
被排除、`.env.example` **不**被排除），并额外检查 `.env` 里没有残留测试占位符。

这条新检查做过**敏感性验证**：把 `.gitignore` 的 `.env` 规则改坏后，自检如期报
`FAIL .env 被 gitignore 排除` 并返回非零；恢复后重新全通过。


7.2 证明的是「能连上」；这一节证明的是「**连不上时不崩**」。用**格式合法但不可达**的
HTTPS 地址写真实 `.env`、真实执行 `app.py`、在浏览器里观察。

> 补充：这条回退路径后来在 7.2 的 Paratera 限流场景中被**真实触发**过一次
> （`RateLimitError`），界面表现与本节的预测一致 —— 不是只在构造场景里成立。

脚本结束后会删除 `.env`（若原本存在则还原），保证仓库回到无密钥状态。

| 检查 | 实测 |
| --- | --- |
| 写入临时 `.env`（含在线配置） | 已写入 |
| 服务以在线配置启动成功 | HTTP 200 |
| 首页正常渲染 | ≥4 张统计卡 |
| 设置页报告为 **GenAI 在线** 模式 | 是 |
| 设置页显示配置的模型 ID | `e2e-placeholder-model` |
| **设置页不回显 API Key** | 占位密钥未出现在页面文本中 |
| **连接失败后明确报告已回退 Mock** | `在线调用失败，已回退 Mock · 原因类别：APIConnectionError` |
| 报告了失败原因类别 | `APIConnectionError` |
| **未把 Mock 伪装成在线成功** | 不出现“连接成功（在线模型）” |
| 在线失败时仍可开始诊断 | 题卡正常出现 |
| `.env` 已还原为无密钥状态 | 已删除 |

脚本结束后会删除 `.env`（若原本存在则还原），保证仓库回到无密钥状态。

| 检查 | 实测 |
| --- | --- |
| 写入临时 `.env`（含在线配置） | 已写入 |
| 服务以在线配置启动成功 | HTTP 200 |
| 首页正常渲染 | ≥4 张统计卡 |
| 设置页报告为 **GenAI 在线** 模式 | 是 |
| 设置页显示配置的模型 ID | `e2e-placeholder-model` |
| **设置页不回显 API Key** | 占位密钥未出现在页面文本中 |
| **连接失败后明确报告已回退 Mock** | `在线调用失败，已回退 Mock · 原因类别：APIConnectionError` |
| 报告了失败原因类别 | `APIConnectionError` |
| **未把 Mock 伪装成在线成功** | 不出现“连接成功（在线模型）” |
| 在线失败时仍可开始诊断 | 题卡正常出现 |
| `.env` 已还原为无密钥状态 | 已删除 |

## 8. 真实进程级端到端（`tools/e2e_restart_check.py`）

`tests/test_acceptance.py` 的场景 C 是在**同一个 Python 进程内**重新打开数据库文件。
本节验证的是更接近用户实际承诺的一条链路：**真的杀掉 Gradio 服务进程、重新启动**。

脚本自己管理服务进程（按端口定位并结束进程，不按进程名匹配），执行流程与实测结果：

| 阶段 | 检查 | 实测 |
| --- | --- | --- |
| 1 | 起始数据库已清空 | 文件不存在 |
| 1 | 服务启动成功 | HTTP 200 |
| 1 | 启动后无作答记录 | `attempts=0` |
| 1 | 浏览器完成一题作答 | `PHY-000021` |
| 1 | 提交后出现判分反馈 | `✓ 正确`，含知识点「波速与频率」 |
| 1 | 数据库已写入作答 | `attempts=1` |
| 1 | 已写入掌握度记录 | `mastery=1` |
| 2 | 服务已停止 | 端口无监听 |
| 2 | 重新启动成功 | HTTP 200 |
| 2 | 数据库文件仍然存在 | 是 |
| 2 | **重启后作答记录未丢失** | `(1, 1, 1) -> (1, 1, 1)` |
| 2 | 首页仍显示今日作答（界面层） | `今日作答 1 近七天正确率 100%` |
| 2 | 重启后图表仍画出柱子 | `[0,0,0,0,0,0,110]` |
| 2 | 错题页可读取历史 | 表格含题目 ID / 作答时间 / 原题等表头 |

截图：`data/e2e-check/e2e-01-after-answer.png`、`e2e-02-after-restart.png`、
`e2e-03-dashboard-final.png`。

## 9. 交付前自检（`tools/preflight_check.py`）

| 组 | 检查项 |
| --- | --- |
| 密钥 | 源码无硬编码密钥、`.env` 未提交且已 gitignore、`.env.example` 存在、gitignore 排除库文件 |
| 内容 | 知识树 59 节点 / 最大层级 5 / 父节点与前置引用有效 / 父链无环；题库 30 道 / 全部原创 / 无伪造教材引用 / 每题有解析；科目分布 10·6·4·4·6 |
| 判分 | 全部客观题标准答案自判为正确；6 类攻击输入均返回 `uncertain` |
| 端到端 | 全新数据库导入知识树与题库、题卡不含答案、判分正确、重复提交只留 1 行、今日统计、七天序列、掌握度未被视为完全掌握、无密钥时 Mock |
| 告警 | 构造整个界面时本项目代码零告警（上游 Gradio 迁移提示单独计数） |

> 密钥扫描器与告警检查都做过**敏感性验证**：故意植入
> `GENAI_API_KEY="sk-abcdef..."` 与 `warnings.warn('probe-own-warning')` 后，
> 两项检查都如期失败，随后已移除探针。这不是空转的检查。

## 10. 已知未覆盖项

1. 题目配图渲染（种子题库没有配图，字段已预留）。
2. 数千题规模的导入性能与分页。
3. 时间旅行类测试（间隔复习按真实时间推进，未用可注入时钟验证 14 天后的到期行为）。
4. 多用户并发（当前为单用户本地模式，`(user_id, token)` 唯一约束已为扩展预留）。
5. 未在真实网络下验证限流/退避对上游 429 的行为（`MockTransport` 覆盖了超时与连接错误，
   真实端点验证覆盖了正常响应，但没有刻意触发 429）。
6. 未做长时间运行的内存与连接泄漏观测（仅确认 `build_app` 不产生本项目告警）。
7. 视觉复核覆盖 10 张截图；滚动后才会出现的内容、以及交互过程中的中间态未逐帧复核。

## 11. 结论边界

本报告能证明的是：**在上述环境与上述命令下，
133 个自动化用例、25 项浏览器检查、10 张截图的视觉模型复核、6 项像素检查、
14 项进程级重启检查、16 项真实 GenAI 在线检查、11 项在线回退检查与交付前自检全部通过。**

它**不能**证明：

- 判分对**任意**物理表达式都正确。只证明了对 30 道种子的标准答案、已知等价变形与
  错误反例正确，且已知攻击输入被拒。
- 题目物理内容经过**人工专家审核**（`verification.human_review=false`，
  种子题是程序化生成的原创题并做过数学自检）。
- 界面在**所有**分辨率与浏览器下都正常。只测了 Chromium 的 1440×1000 与 390×844。
- 视觉评审是**穷尽**的。视觉模型报告“无排版缺陷”只代表它在那 10 张图上没看到问题，
  且有抄录错误（见 6.4 节），不能替代人工审美判断。
- 学校 GenAI 在**长期/高并发**下稳定。只做了单次连通与单次问答验证。
