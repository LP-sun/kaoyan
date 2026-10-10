# PhysicsPrep 架构说明

本文说明代码分层、数据库设计、判分流水线与安全边界。诊断算法的具体公式见
[DIAGNOSIS_ALGORITHM.md](DIAGNOSIS_ALGORITHM.md)，测试证据见 [TEST_REPORT.md](TEST_REPORT.md)。

## 1. 分层

```text
app.py / tools
   │  仅负责启动与运维脚本
   ▼
physics_prep/ui/            Gradio Blocks 界面（6 个标签页）
   │  只做渲染与事件转发；不直接写 SQL
   ▼
physics_prep/services/     业务编排（事务、会话、学习记录、大纲归档）
   │
   ├── physics_prep/diagnosis/   判分、选题、掌握度、错因（纯函数，可单测）
   ├── physics_prep/questions/   题库与知识树校验、导入导出
   └── physics_prep/llm/         大模型抽象（在线 / Mock / 提示词）
   ▼
physics_prep/database/     SQLAlchemy 2.x 模型、会话工厂、版本化迁移
```

依赖方向始终向下，`diagnosis` 不依赖 `ui`，因此判分逻辑可以脱离界面单独测试。
`llm` 也不被 `diagnosis` 依赖：**没有 API Key 时判分与诊断完全不受影响**。

### 各模块职责

| 模块 | 职责 | 关键约束 |
| --- | --- | --- |
| `ui/quiz.py` | 题卡渲染、反馈文案 | 只接收 `_public()` 过滤后的字段 |
| `ui/dashboard.py` | 统计卡与 Plotly 图表 | 无掌握度时显示“尚无记录” |
| `ui/knowledge_tree.py` | 知识树层级展示、导入导出 | 导出不含掌握度 |
| `ui/wrong_answers.py` | 错题表、历次作答对比、复习计划 | 全部来自 `attempts` 快照 |
| `ui/settings.py` | 模式说明、连接测试、备份入口 | 密钥永不回显 |
| `services/learning.py` | 会话/提交/统计事务 | 提交使用 `BEGIN IMMEDIATE` + token 唯一约束 |
| `services/syllabus.py` | 大纲按 SHA256 归档 | 不认定官方年度 |
| `diagnosis/math_grader.py` | 确定性数学判分 | 无 `eval`、无 `parse_expr`、无子进程 |
| `diagnosis/selector.py` | 可解释自适应选题 | 覆盖优先、避免同题循环；自适应诊断只主动派发可确定性判分的题型 |
| `diagnosis/mastery.py` | 掌握度启发式估计 | 明确不是校准过的 BKT/IRT |
| `diagnosis/units.py` | 保守单位提示 | 只提示，不直接判错 |
| `questions/validator.py` | 题目字段校验 | 缺字段/字段非法直接拒绝 |

## 2. 数据库

SQLite 单文件，默认位于 `data/physics_prep.sqlite3`（可用 `PHYSICSPREP_DB_PATH` 覆盖）。

| 表 | 说明 |
| --- | --- |
| `users` | 默认单用户，主键固定为 `local`，保留 ID 便于将来扩展 |
| `topics` / `topic_prerequisites` | 知识树节点与前置依赖（四级以上） |
| `questions` / `question_topics` | 题目以 `payload` JSON 存储 + 索引列；`version` 随修改递增 |
| `exam_sessions` | 一次诊断会话；`current_snapshot` 保存“当前待答题”以便恢复 |
| `attempts` | 每次提交一条记录，含题目与判分快照；`(user_id, token)` 唯一 |
| `mastery_records` | 按用户 × 知识点保存掌握度证据 |
| `review_schedule` | 间隔复习到期时间 |
| `llm_usage` | 大模型调用记录（模型、操作、成功与否、tokens） |
| `question_marks` | 题目标记（重启保留） |
| `schema_migrations` | 已应用的迁移版本 |

### 迁移机制

`physics_prep/database/migrations/__init__.py` 中的 `MIGRATIONS` 是 `(version, description, callable)`
的有序元组，只允许追加。`run_migrations()` 读取 `schema_migrations` 中已有版本，仅执行缺失项，
因此**重复启动是幂等的**；每个迁移在自己的事务内执行，失败即回滚。

首项迁移使用 `Base.metadata.create_all()`，后续迁移写成“先检查再修改”的幂等语句，
因此全新数据库与旧数据库走同一条代码路径。这里不使用 Alembic：本项目是单文件 SQLite、
单用户本地运行，显式版本列表比重型迁移框架更容易审计和测试。

### 为什么同时保留 payload 与快照

`questions.payload` 是题目当前定义；`attempts.snapshot` 是**作答当时**的完整题目副本
（含标准答案与解析）。这道题以后被编辑或删除，历史答题记录仍然可以完整解释，
错题本里的题面与解析也不会变。

## 3. 判分流水线

```text
用户提交
  │
  ├─ 选择题 / 多选题 ──► 确定性集合比较（不解析数学）
  │
  ├─ 数值题 / 符号题 ──► math_grader.grade()
  │      │
  │      ├─ 1. 长度 ≤300、AST 节点 ≤100、嵌套 ≤15
  │      ├─ 2. AST 白名单 → SymPy（无 eval / 无 parse_expr）
  │      │     允许：数字、白名单符号、+ - * / **、sqrt/sin/cos/tan/exp/log/abs
  │      │     幂指数必须是 |常量| ≤ 20，字面量 ≤ 1e12
  │      ├─ 3. 单位提示（仅提示，命中即 uncertain 要求核对）
  │      ├─ 4. 精确相等 → 数值容差 → together/cancel/simplify
  │      ├─ 5. 仍带自由符号：正有理数代入寻找反例
  │      └─ 6. 无法证明等价 → uncertain（不强行判错）
  │
  └─ 简答 / 推导题 ──► 恒为 uncertain，交人工确认
```

每一步前后都检查墙钟截止时间（默认 5 秒，可用 `grading_timeout` 覆盖），
超时返回 `uncertain`。早期版本使用 `multiprocessing` 子进程做硬超时，
在受限环境（命名管道不可用）下会整体失败并使判分不可用，现已改为纯进程内实现。

**大模型不参与判分。** `grade()` 的结果是唯一判分依据，模型输出只用于解释与追问；
生成题默认 `verified=False`，未核验题目不进入正式诊断题库。

**自适应诊断只主动派发可确定性判分的题型**（`AUTO_GRADED_TYPES`：选择/多选/数值/符号）。
简答与推导题只能得到 `uncertain`：既不更新掌握度，又占用一次诊断名额，因此不进入
自适应诊断流；它们仍可通过「精确重做题目 ID」主动练习并人工复核。若某个考点子集里
只剩开放题，选择器退回照常派发（避免会话无题可做），判分结果依旧诚实地标记为
`uncertain`。

## 4. 大模型接入

`LLMClient` 抽象有两个实现：

- `OfficialGenAIClient`：OpenAI 兼容 Chat Completions（仅用标准文本补全，
  **不假定**学校 API 支持原生 Tool Calling 或 JSON Schema 结构化输出）；
- `MockLLMClient`：离线确定性教师，输出带 `【Mock 教师，非模型推理】` 前缀。

在线客户端的行为：

- 只接受 `https://` 且带主机名的 Address，否则抛 `LLMUnavailable`，`create_client` 回退 Mock；
- 请求带超时、指数退避重试（`min(8, 2**attempt)`）、`threading.BoundedSemaphore(2)` 限流；
- 失败时**只**保留异常类别名，不记录请求体、URL、响应正文或认证头；
- 超过 6000 字符的提问直接拒绝（`input_limit`），不发起请求；
- 模型返回空内容视为失败，同样回退。

提示词集中在 `llm/prompts.py`，按作答阶段区分 system 提示：
`TUTOR_SYSTEM_BEFORE_SUBMIT`（只给提示，不公布答案）、
`TUTOR_SYSTEM_AFTER_SUBMIT`、`TUTOR_SYSTEM_FULL_SOLUTION`（用户明确索要才给）。

## 5. 界面状态与答案隔离

Gradio 的 `gr.State` 只保存 `sid`（会话 ID）、`qid`（题目 ID）、`token`（一次性提交标识）
和已提交的反馈文本。**题目对象本身（含标准答案与解析）从不进入前端状态**：

1. `LearningService._public()` 只挑选 `id/subject/topic_ids/difficulty/question_type/stem/options/...` 字段；
2. 判分发生在服务端，`submit()` 返回的反馈里才第一次出现标准答案；
3. 每次切题都会清空反馈、解析、AI 回答与提示，避免显示上一题的状态。

`tests/test_acceptance.py` 与 `tests/test_ui.py` 都断言了“作答前拿不到答案”，
浏览器检查脚本也断言页面上作答前不存在“标准答案 / 推导与检验”文本。

### 事件处理器的命名约定

界面所有事件都经过 `application.py` 里的 `safe()` 包装，把服务异常转成界面可读的
`gr.Error`。`safe()` 使用 `functools.wraps` 并允许显式传入名字：

```python
submit_btn.click(safe(submit), [sid, qid, token, ...], [...])
connection_btn.click(safe(connection, 'connection'), outputs=connection_result)
```

这不是装饰性细节，而是**可测试性的前提**。Gradio 会把注册的处理器放进 `app.fns`，
若不保留函数名，58 个处理器全部会退化成 `wrapped`、`wrapped_1` … `wrapped_47`，
只能靠注册顺序猜哪个是 `submit`、哪个是 `restore`。保留名字后：

- 测试可以按语义名取到处理器，直接验证界面接线（见 `tests/test_online_mode.py`）；
- Gradio 自带的 `/api` 文档页面显示可读的端点名，而不是精灵语名字；
- `tests/test_online_mode.py::test_handlers_are_addressable_by_name` 会防止这一点退化。

`safe()` 对异常的处理也遵循安全边界：`ValueError/KeyError/TypeError` 的消息会截断到
350 字符后显示（这类消息来自校验逻辑，本身就是给用户看的），其余异常一律替换成通用
提示，避免把路径、配置或响应正文带到前端。

## 6. 并发与一致性

- `LearningService.lock` 是进程内 `RLock`；跨进程/多线程的重复提交由
  `attempts` 表的 `(user_id, token)` 唯一约束与 `BEGIN IMMEDIATE` 写锁共同兜底；
- 同一 token 重复提交返回首次的反馈，不会产生第二条记录；
- SQLite 使用 `WAL` + `busy_timeout=30000` + `foreign_keys=ON` + `synchronous=NORMAL`；
- 备份使用 `sqlite3.Connection.backup()`（在线一致性备份），恢复前做
  `PRAGMA integrity_check` 与表结构校验，拒绝非 PhysicsPrep 备份。

## 7. 安全边界

| 要求 | 实现 |
| --- | --- |
| 不硬编码密钥 | 只从 `.env` / 环境变量读取；`.env` 在 `.gitignore` |
| 不泄露密钥 | 界面只显示长度与末四位（短于 12 字符只显示长度）；错误信息只留异常类别 |
| 不上传学习数据 | 只有用户主动输入的提问会发给模型；教材、题库、学习记录都不发送 |
| 不绕过访问控制 | 只使用标准 HTTPS Chat Completions，不做任何绕过或并发突破 |
| 不伪造教材内容 | 种子题 `source_type` 全为 `original`、`source_reference` 为 `null` |
| 不伪造官方大纲 | 大纲只按 SHA256 归档，状态标注“用户导入，年份与官方有效性待核” |
| 默认只监听本机 | `app.py` 固定 `server_name='127.0.0.1'`，`share=False` |
| 不执行不可信代码 | 数学输入经 AST 白名单，无 `eval`；无 shell 调用 |

## 8. 已知限制

1. 题目图片字段（`image`/`images`）已预留但当前种子题库没有配图，界面不渲染图。
2. 复杂多步推导只能人工确认；第一版没有手写数学公式编辑器。
3. 复习间隔是启发式规则，未使用 FSRS 或 Anki 同步。
4. 单用户本地运行，没有账号体系与权限控制（保留了 `user_id` 字段）。
5. 知识树与题库导入是“整批提交”，超大题库（数万题）未做分页优化。
6. 判分是进程内实现，没有操作系统级资源隔离（早期用 `multiprocessing` 硬超时的方案
   在命名管道受限的环境中会让**全部判分失效**，已弃用）。风险改由解析前的输入上限
   与每步墙钟截止时间控制，详见 [`TEST_REPORT.md`](TEST_REPORT.md) 第 3 节。
7. 依赖 Gradio 5.x。Gradio 6.0 会移除 `Blocks(theme=...)`、`Blocks(css=...)`、
   `gr.HTML` 的隐式 `padding` 默认值与 `row_count` 元组用法；升级前需要按上游迁移说明调整。
   当前这些提示由 `tools/preflight_check.py` 单独计数，不计为项目自身告警。

## 9. 验证工具

| 工具 | 作用 | 覆盖 |
| --- | --- | --- |
| `tests/` | pytest 用例 | 133 项：判分、后端、视图、在线模式、验收场景 |
| `tools/preflight_check.py` | 交付前自检 | 密钥扫描、知识树完整性、端到端冒烟、自身零告警 |
| `tools/ui_visual_check.py` | 真实浏览器交互检查 | 25 项 DOM 断言 + 10 张截图 |
| `tools/check_render_pixels.py` | 像素级渲染检查 | 6 项：图表尺寸/数据点/刻度/墨水比例/居中 |
| `tools/vision_review.py` | 视觉验收（委托图像模型） | 10 张截图逐张描述 |
| `tools/vision_spotcheck.py` | 视觉定向复核 | 图表是否空坐标轴、窄屏是否溢出 |
| `tools/e2e_restart_check.py` | 进程级重启验收 | 14 项：答题 → 杀服务 → 重启 → 记录仍在 |
| `tools/e2e_online_school_check.py` | 真实 GenAI 在线验收 | 16 项：真实凭据 + 真实网络 + 真实模型回答 |
| `tools/e2e_env_fallback_check.py` | 在线但不可达的回退验收 | 11 项：不崩、明确告知、回退 Mock |
| `tools/probe_model_channels.py` | 模型通道探测 | 只报凭据存在性与模型列表，不打印密钥 |
| `tools/dump_dom.py` | 转储已渲染 DOM | 排查 Gradio 选择器变化 |
| `tools/count_tests.py` | 用例计数 | 按文件统计 |

### 模型降级链

`GENAI_MODEL` 是主模型，`GENAI_MODEL_FALLBACKS` 是逗号（或分号）分隔的备用模型。
`Settings.models` 把它们解析成**有序去重**的模型链，主模型永远排第一。

降级与否由错误的**性质**决定，而不是「失败了就换下一个」：

| 情况 | 重试（同模型） | 降级（换模型） | 实测依据 |
| --- | --- | --- | --- |
| 模型不存在 404 | ✅ | ✅ | 学校端点 `DeepSeek-V3.2` → 404 未找到模型节点 |
| 无权限 403 | ✅ | ✅ | 学校端点 `deepseek-chat` → 403 该模型无使用权限 |
| 限流 429 | ✅ | ✅ | Paratera 共享 key 并发时实际触发过 |
| 返回空内容 | ✅ | ✅ | Paratera `DeepSeek-V4-Flash` 实测返回空 content |
| 超时 | ✅ | ❌ | 同一端点换模型大概率同样慢，只会多花时间 |
| 连接失败 / DNS / 代理 | ✅ | ❌ | 换模型必然同样失败 |
| 认证失败 401 / 欠费 402 | ❌ | ❌ | 配置问题，等多久都不会好，立刻回退 |

保守原则是**拿不准就不降级**：降级意味着再打一次付费请求，
而把「认证配错」误判成「模型不可用」会白白多花 N 倍调用。

一次调用的最坏情况是 `模型数 × (max_retries + 1)` 次请求，
换模型之间只停顿 `SWITCH_MODEL_DELAY_SECONDS`（1 秒），不做长退避。

`ask()` 的返回值里 `model` 是**真正给出文本的模型**，`attempted_models` 是尝试顺序。
界面据此明确告知「已降级到 X」，而不是假装一切正常。


DOM 断言能证明「元素存在」，像素统计能证明「区域非空」，两者都证明不了「看起来是否乱」。
本项目在 `build_app` 里给关键组件加了 `elem_id`（`quiz-options`、`feedback-card`、
`connection-result`、`ai-prompt`、`ai-btn`、`ai-response` 等），既服务于 Playwright 断言，
也让视觉验收脚本能精确定位区域。

需要图像判断的部分交给 `tools/vision_review.py`：它把截图以 data URI 形式发给
具备图像输入能力的模型。**注意 `GLM-4.6V` 是推理型模型**，`max_tokens` 给得太小会把
预算全花在内部推理上、`content` 返回空字符串，看起来像“模型不支持图像”；
默认预算必须给到 4000。
