# PhysicsPrep · 物理考研 AI 自适应诊断与复习平台

面向中国硕士研究生入学考试**物理专业课**的本地学习平台：普通物理（力学、电磁学、热学、
振动与波动、光学）与量子力学。以**交互式答题页面为核心产品**，而不是一个聊天框。

- 本地网页（Gradio Blocks），只监听 `127.0.0.1`，默认不开启公开分享链接
- SQLite 持久化：关闭程序后重新启动，历史记录、掌握度、错题全部还在
- 确定性判分：选择题比选项，计算题用 SymPy 判断表达式等价
- 可解释的自适应选题：覆盖未测考点、答错后补救前置知识、避免同题循环；
  诊断只主动派发可确定性判分的题型（选择/多选/数值/符号），简答推导题留作显式练习
- **没有 API Key 也能用**：自动进入 Mock 模式，判分/诊断/记录全部正常

诊断算法细节见 [`docs/DIAGNOSIS_ALGORITHM.md`](docs/DIAGNOSIS_ALGORITHM.md)，
架构与安全边界见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)，
测试证据见 [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md)。

---

## 快速开始（3 步）

```bash
cd PhysicsPrep

# 1) 建虚拟环境并安装依赖（Python 3.11+，本项目在 3.12.14 上验证）
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .        # Windows
# source .venv/bin/activate && pip install -e .     # macOS / Linux

# 2) 启动（无 .env 也能直接跑，自动 Mock 模式）
.venv\Scripts\python.exe app.py

# 3) 浏览器打开
#    http://127.0.0.1:7860
```

首次启动会自动创建数据库 `data/physics_prep.sqlite3`，并导入初始知识树（59 个知识点，
四级以上层级）与 **30 道人工编写并核验的原创题**。

### 开始第一轮物理考研诊断

1. 打开 `http://127.0.0.1:7860`，首页「学习总览」会显示今日建议与待复习内容（首次为空）。
2. 切到 **「开始诊断」** 标签页。
3. 在「科目」下拉里选 **力学**（或留空 = 全部科目）；也可以直接选具体知识点（如
   `纯滚动约束 · PHY-MECH-ROT-003`）做定点练习。
4. 点 **「开始诊断」**。页面中央出现题卡，公式以 LaTeX 渲染。
5. 单选题点选项；多选题勾选；数值/符号题在文本框输入表达式（**乘号要显式写出**，例如
   `sqrt(2*g*h)`、`2*g*sin(theta)/3`、`M*g*sin(theta)/(M+I/R**2)`）。
6. 卡住时点 **「给我一个提示」**（只给方向，不会公布答案）。
7. 点 **「提交答案」** → 立刻看到 正确 / 需要巩固 / 需要人工确认 + 标准答案 + 推导 +
   关联知识点 + 错因判断 + 掌握度更新 + 下次复习时间。
8. 点 **「下一题」** 继续（系统按你的表现选题）；点 **「查看本轮诊断报告」** 看本轮统计。
9. 切到 **「知识树」** 看层级结构与掌握度，**「错题与复习」** 看错题、对比历次作答、
   查看复习计划。
10. 关闭程序后重新 `python app.py`，点首页的 **「继续上次学习」** 即可回到未答完的题。

---

## 配置 GenAI

系统读取项目根目录的 `.env`：

```bash
copy .env.example .env      # Windows
# cp .env.example .env      # macOS / Linux
```

`GENAI_MODEL` 是主模型，`GENAI_MODEL_FALLBACKS` 是备用模型（逗号分隔）。
主模型失败且**错误类型表明换模型有意义**时，会按顺序降级：

```env
GENAI_MODEL=DeepSeek-V4-Flash
GENAI_MODEL_FALLBACKS=DeepSeek-V4.1-Flash,Kimi-K2.6,Qwen3.8-Flash
```

| 情况 | 同模型重试 | 换下一个模型 |
| --- | --- | --- |
| 模型不存在 404 / 无权限 403 / 限流 429 / 返回空内容 | ✅ | ✅ |
| 超时 | ✅ | ❌（同一端点换模型大概率同样慢） |
| 连接失败 / DNS / 代理错误 | ✅ | ❌（换模型必然同样失败） |
| 认证失败 401 / 欠费 402 | ❌ | ❌（配置问题，立刻回退） |

界面会明确告知降级结果，例如
`连接成功（在线模型） · 实际使用：DeepSeek-V4.1-Flash`，
而不是假装一切正常。想验证降级真的生效：

```bash
# 故意把主模型改成不存在的 ID，看是否自动降级到备用模型
.venv\Scripts\python.exe tools/e2e_online_school_check.py --break-primary
```

上海科技大学 GenAI 的可用配置（已实测连通）：


```env
GENAI_API_KEY=<学校提供的 Key>
GENAI_BASE_URL=https://genaiapi.shanghaitech.edu.cn/api/v1/start
GENAI_MODEL=deepseek-v4-pro
GENAI_TIMEOUT=60
GENAI_MAX_RETRIES=2
APP_MOCK_MODE=false
```

- `GENAI_BASE_URL` 填到 `/api/v1/start` 即可，OpenAI SDK 会自动补 `/chat/completions`。
- 可用的模型 ID 需以实际授权为准：`deepseek-v4-pro` 已验证可用；
  `deepseek-chat` 返回 403「该模型无使用权限」。
- 首次响应可能超过 30 秒（冷启动），属正常现象。

**借用同工作区其他项目已有的凭据。** 如果 `fastgpt-physics-lab/env/.env` 里已经配好
`GENAI_*`，可以一条命令把两套凭据都写进本项目的 `.env`（该脚本是幂等的，
旧的 `.env` 会先备份为 `.env.bak`）：

```bash
# A 组（生效）：Paratera 聚合端点 + 模型降级链，来自 fastgpt-physics-lab/env/.env
# B 组（注释备用）：上科大校内直连，来自 DSH 本机凭据库
.venv\Scripts\python.exe tools/setup_env_from_sources.py
```

也可以不复制、直接借用（只读，不落盘到本项目）：

```bash
.venv\Scripts\python.exe tools/verify_with_lab_env.py
.venv\Scripts\python.exe tools/e2e_online_school_check.py --env-file ..\fastgpt-physics-lab\env\.env
```

这些命令都已实测通过（Paratera + `DeepSeek-V4-Flash`，16/16；降级验证 16/16）。

> ⚠ `PhysicsPrep/.env` 一旦存在就**含真实密钥**：已被 `.gitignore` 排除，
> 但不要外发、不要贴进聊天记录、不要提交。

**注意**

- `GENAI_BASE_URL` 必须填写学校提供的实际地址；**不要猜测模型 ID**。
- 三个变量（KEY / BASE_URL / MODEL）任一为空 → 自动 Mock 模式。
- `.env` 已在 `.gitignore` 中，**绝不会**被提交。
- 界面里可以临时修改 Address、模型 ID、超时与重试次数，但**密钥只从环境变量读取，
  界面既不接收也不显示完整密钥**（只显示长度与末四位，短密钥只显示长度）。
- 只使用标准 Chat Completions 接口，不假定学校 API 支持 Tool Calling 或
  JSON Schema 结构化输出。若接口不兼容，界面会显示明确的错误类别并回退到 Mock。
- 修改 `.env` 后需重启；界面上的「应用本次运行配置」只影响当前进程。

### 测试 GenAI 连接

界面 → **「设置与备份」** 标签页 → 点 **「测试模型连接」**。三种结果会被明确区分：

- `连接成功（在线模型）`
- `在线调用失败，已回退 Mock · 原因类别：<异常类名>`
- `当前为 Mock 模式（未发起在线请求）`

也可以查看当前模式、API Address、模型 ID、超时、重试次数与密钥脱敏状态。

### 切换到 Mock 模式

任选其一：

- `.env` 中设 `APP_MOCK_MODE=true`
- 留空 `GENAI_API_KEY`（或 BASE_URL / MODEL）
- 界面「设置与备份」勾选「强制使用 Mock」

Mock 模式下不发起任何网络请求，判分、诊断、错题、复习计划全部正常，
AI 教师的回答会带 `【Mock 教师，非模型推理】` 前缀。

---

## 功能一览

| 标签页 | 功能 |
| --- | --- |
| 学习总览 | 今日作答、近七天正确率、待复习考点、最近七天柱状图、薄弱考点、最近诊断、继续上次学习 |
| 开始诊断 | 题卡（LaTeX）、单选/多选/数值/符号作答、提示、提交判分、解析、下一题、标记、AI 教师 |
| 知识树 | 四级以上层级结构、掌握度、按考点练习、知识点增删改、JSON/YAML/CSV 导入、导出 |
| 错题与复习 | 错题表（原题/你的答案/标准答案/解析）、按考点筛选、精确重做、历次作答对比、复习计划 |
| 题库管理 | 列表与搜索、按科目/考点/难度筛选、JSON 编辑、导入导出 CSV/JSON、审核状态记录 |
| 设置与备份 | 模式说明、连接测试、配置、SQLite 备份与恢复、大纲版本归档 |

---

## 题库导入

### 题目（JSON / CSV）

「题库管理」→「导入 JSON / CSV」→ 选文件 →「校验并导入」。

JSON 为数组：

```json
[
  {
    "id": "PHY-100001",
    "subject": "mechanics",
    "topic_ids": ["PHY-MECH-ROT-003"],
    "difficulty": 2,
    "question_type": "symbolic",
    "stem": "题干文本，公式用 $...$ 或 $$...$$",
    "options": [],
    "correct_answer": "2*g*sin(theta)/3",
    "solution": "解答与独立检验",
    "hint": "可选提示",
    "allowed_symbols": ["g", "theta"],
    "positive_symbols": ["g", "theta"],
    "expected_unit": null,
    "numeric_tolerance": 1e-6,
    "source_type": "original",
    "source_reference": null,
    "verified": true
  }
]
```

字段说明

| 字段 | 说明 |
| --- | --- |
| `question_type` | `single_choice` / `multiple_choice` / `numeric` / `symbolic` / `short_answer` |
| `options` | 选择题的选项数组；`correct_answer` 单选为 `"A"`，多选为 `["A","C"]` |
| `topic_ids` | 必须已存在于知识树，否则导入被拒绝 |
| `allowed_symbols` | 该题允许的符号白名单（缺省时从标准答案自动提取） |
| `positive_symbols` | 声明为正实数的符号（影响 `sqrt(L**2)=L` 这类化简） |
| `expected_unit` | 若填写，单位不符将返回“需要人工确认”而不是判错 |
| `source_type` | `official_exam` / `textbook` / `original` / `ai_generated` |
| `verified` | 只有 `true` 的题目才进入诊断选题 |

**来源与审核规则**

- `ai_generated` 的题目导入时**强制** `verified=false`；只能通过
  「题库管理 → 记录明确审核结果」填写审核依据后才能进入诊断题库。
- `official_exam` 与 `frozen=true` 的题目**不进入诊断选题**（冻结模拟卷）。
- `short_answer`（简答/推导题）**不进入自适应诊断**：确定性判分器对它只能给出
  `uncertain`，无法提供掌握度信号。它仍可通过「精确重做题目 ID」主动练习；
  若某考点子集只剩开放题，选择器会退回派发而不是让会话无题可做。
- 本题库的 30 道题全部是 `source_type=original`、`source_reference=null`，
  即人工编写的原创题，**不是**任何真题或教材原题。
- 本系统不伪造教材原文、页码或例题编号；参考教材只用于确定知识结构范围。

CSV 格式：一行一题，`topic_ids` / `options` 用 JSON 数组字符串（如 `["PHY-MECH-ROT-003"]`）。

### 知识树（JSON / YAML / CSV）

「知识树」→「导入知识树 JSON」→「校验并导入知识树」。

```json
[
  {"id": "PHY-MECH-ROT", "name": "刚体动力学", "parent_id": "PHY-MECH",
   "prerequisite_ids": ["PHY-MECH-DYN"], "difficulty": 3, "source_references": []},
  {"id": "PHY-MECH-ROT-003", "name": "纯滚动约束", "parent_id": "PHY-MECH-ROT",
   "prerequisite_ids": ["PHY-MECH-ROT-002"], "difficulty": 3, "source_references": []}
]
```

父节点不存在、出现环（父链或前置依赖）都会被拒绝并给出错误信息。

---

## 数据库与备份

| 项目 | 位置 |
| --- | --- |
| 数据库文件 | `data/physics_prep.sqlite3`（可用环境变量 `PHYSICSPREP_DB_PATH` 覆盖） |
| 初始知识树 | `data/seed_topics.json` |
| 初始题库 | `data/seed_questions.json` |
| 大纲归档 | `data/syllabi/`（按 SHA256 保存，附 `versions.json` 索引） |

`.gitignore` 已排除 `*.sqlite3`、`.env`、`data/backups/` 等，**学习记录与密钥都不会进仓库**。

### 备份学习记录

界面 →「设置与备份」→ **「备份当前数据库」** → 下载 `learning-backup.sqlite3`。
备份是完整的 SQLite 副本（含题库与全部学习记录），**不含 API 密钥**。

也可直接复制数据库文件：

```bash
copy data\physics_prep.sqlite3 D:\backup\physics_prep-2026-10-08.sqlite3
```

### 恢复

「设置与备份」→ 上传备份文件 → 勾选确认 →「恢复备份」。
系统会先做 `PRAGMA integrity_check` 与表结构校验，拒绝损坏或非本项目的文件。
恢复会**整体替换**当前数据库，请先备份当前数据。

### 数据迁移

启动时自动运行 `physics_prep/database/migrations/` 中未应用的迁移，重复启动是幂等的。
当前版本 3 项迁移。表结构变更以追加迁移的方式记录，不修改历史迁移。

---

## 测试

```bash
.venv\Scripts\python.exe -m pytest                     # 133 passed
.venv\Scripts\python.exe -m pytest -v
.venv\Scripts\python.exe -m pytest --junitxml=report.xml   # 最可靠的计数方式
.venv\Scripts\python.exe tools/count_tests.py              # 统计用例数
.venv\Scripts\python.exe tools/preflight_check.py          # 交付前自检
```

`tools/preflight_check.py` 会检查：源码无硬编码密钥、`.env` 未被提交、知识树层级与引用完整性、
题目来源标注、全部客观题标准答案自判、攻击输入被拒、全新数据库端到端流程、
掌握度未被“一次答对即视为掌握”，以及**本项目代码自身不产生任何警告**。

真实浏览器检查与进程级重启验收（需要额外安装 Playwright，不影响应用本身）：

```bash
.venv\Scripts\python.exe -m pip install -e ".[ui-check]"

# 浏览器视觉/交互检查（25 项）+ 像素检查（6 项）
.venv\Scripts\python.exe app.py                                            # 终端 1
.venv\Scripts\python.exe tools/ui_visual_check.py http://127.0.0.1:7860    # 终端 2
.venv\Scripts\python.exe tools/check_render_pixels.py http://127.0.0.1:7860

# 真实进程级端到端：答题 → 杀掉服务 → 重启 → 记录仍在（14 项）
# 注意：该脚本会自己启动/停止 WORKDIR 下的 app.py，不要与上面的服务抢同一端口
.venv\Scripts\python.exe tools/e2e_restart_check.py http://127.0.0.1:7861

# 在线配置启动与回退（11 项）：临时写入 .env → 真实启动 → 浏览器检查 → 还原 .env
.venv\Scripts\python.exe tools/e2e_env_fallback_check.py http://127.0.0.1:7863

# 真实学校 GenAI 在线验收（16 项）：用真实凭据与真实网络问答，结束即还原 .env
# 需要本机已配置 DEEPSEEK_API_KEY（脚本从 DSH 凭据库读取，不打印密钥）
.venv\Scripts\python.exe tools/e2e_online_school_check.py http://127.0.0.1:7864

# 视觉验收：把截图交给具备图像能力的模型逐张描述（需要 PARATERA_API_KEY）
.venv\Scripts\python.exe tools/vision_review.py data/ui-check data/vision-review 4000
.venv\Scripts\python.exe tools/vision_spotcheck.py data/ui-check
```

截图与报告输出到 `data/ui-check/`，重启验收截图输出到 `data/e2e-check/`。

---

## 项目结构

```text
PhysicsPrep/
├── app.py                      启动入口（固定 127.0.0.1，不开启 share）
├── pyproject.toml              依赖与 pytest 配置
├── .env.example / .gitignore
├── README.md
├── physics_prep/
│   ├── config.py               环境变量 → Settings
│   ├── clock.py                统一 UTC 时间
│   ├── database/
│   │   ├── models.py           10 张表（SQLAlchemy 2.x）
│   │   ├── session.py          引擎/会话工厂、PRAGMA 配置
│   │   └── migrations/         版本化、可重复执行的迁移
│   ├── llm/
│   │   ├── client.py           LLMClient / OfficialGenAIClient / create_client
│   │   ├── mock.py             MockLLMClient（离线确定性）
│   │   └── prompts.py          提示词（作答前/后/完整解析/错因）
│   ├── diagnosis/
│   │   ├── engine.py           错因类别与判定
│   │   ├── mastery.py          掌握度启发式估计 + 复习间隔
│   │   ├── selector.py         自适应选题
│   │   ├── math_grader.py      SymPy 确定性判分（AST 白名单）
│   │   └── units.py            保守单位提示
│   ├── questions/
│   │   ├── repository.py       题库与知识树 CRUD、导入导出
│   │   ├── validator.py        字段校验
│   │   └── importer.py         导入入口
│   ├── services/
│   │   ├── learning.py         会话/提交/统计事务编排
│   │   └── syllabus.py         大纲 SHA256 版本归档
│   └── ui/
│       ├── application.py      Gradio Blocks 装配（6 个标签页）
│       ├── quiz.py             题卡与反馈渲染
│       ├── dashboard.py        统计卡与 Plotly 图表
│       ├── knowledge_tree.py   知识树视图
│       ├── wrong_answers.py    错题本与复习计划
│       ├── settings.py         模式/连接/备份/大纲
│       └── styles.py           响应式 CSS
├── data/
│   ├── seed_topics.json        初始知识树（59 个知识点）
│   ├── seed_questions.json     30 道原创核验题
│   ├── generate_seed.py        种子数据生成脚本
│   └── validate_seed_math.py   种子题数学自检
├── tools/
│   ├── ui_visual_check.py      Playwright 浏览器检查 + 截图
│   ├── check_render_pixels.py  PIL 像素级渲染检查
│   ├── e2e_restart_check.py    真实进程级重启验收（杀服务 → 重启 → 记录仍在）
│   ├── e2e_env_fallback_check.py  在线配置启动与回退验收（真实 .env + 真实启动）
│   ├── e2e_online_school_check.py 真实 GenAI 在线验收（--env-file 借用凭据 / --break-primary 验证降级）
│   ├── setup_env_from_sources.py  从其他项目与 DSH 凭据生成 .env（幂等，写前备份）
│   ├── verify_with_lab_env.py  用 fastgpt-physics-lab 的 GENAI_* 验证客户端连通性
│   ├── probe_models_available.py  逐个探测模型是否可用（真实网络）
│   ├── inspect_lab_env.py      列出其他项目 .env 的变量名（只报长度与末四位，不打印值）
│   ├── show_env_config.py      显示某个 .env 的 GENAI_* 结构（密钥只报末四位）
│   ├── vision_review.py        视觉验收：把截图交给具备图像能力的模型描述
│   ├── vision_spotcheck.py     视觉定向复核（图表是否空白 / 窄屏是否溢出）
│   ├── probe_model_channels.py 探测可用的模型通道（只报存在性，不打印密钥）
│   ├── preflight_check.py      交付前自检（密钥/知识树/端到端/零告警）
│   ├── dump_dom.py             转储已渲染 DOM（排查选择器）
│   └── count_tests.py          测试用例统计
├── tests/                      133 个用例
└── docs/
    ├── ARCHITECTURE.md
    ├── DIAGNOSIS_ALGORITHM.md
    ├── CONTENT_VALIDATION.md
    └── TEST_REPORT.md
```

---

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `GENAI_API_KEY` | 空 | 学校 GenAI Key；空则 Mock |
| `GENAI_BASE_URL` | 空 | 学校实际 API Address（必须 https） |
| `GENAI_MODEL` | 空 | 学校实际模型 ID |
| `GENAI_TIMEOUT` | 60 | 单次请求超时（秒） |
| `GENAI_MAX_RETRIES` | 2 | 重试次数（指数退避） |
| `APP_MOCK_MODE` | false | true = 强制离线 |
| `PHYSICSPREP_DB_PATH` | `data/physics_prep.sqlite3` | 数据库位置 |
| `PHYSICSPREP_PORT` | 7860 | 监听端口（始终绑定 127.0.0.1） |
| `PHYSICSPREP_OPEN_BROWSER` | false | 启动时自动开浏览器 |

---

## 安全与隐私

- 只监听 `127.0.0.1`，`share=False`，不生成公网链接。
- 密钥只从 `.env` / 环境变量读取，不写入代码、不进入日志、不在界面回显。
- 在线调用失败时只保留异常**类别名**，不打印请求体、URL、响应正文或认证头。
- 只有你在「向 AI 教师提问」里主动输入的文字会发给模型；
  **教材、题库、学习记录都不会上传**。
- 数学输入用 AST 白名单解析，无 `eval`、无 `parse_expr`、无 shell 调用。
- 不绕过任何访问控制或资源限制；不下载非授权扫描版教材。
- 大纲只按 SHA256 归档，状态标注“用户导入，年份与官方有效性待核”，
  不把未核对文件认定为某年度官方大纲。

---

## 已知限制

1. **掌握度是启发式估计**，不是经过校准的 BKT / IRT 测量，也没有效度检验。
2. 简答/分步推导题只能人工确认；没有手写数学公式编辑器（第一版用文本输入）。
3. 复习间隔是启发式规则，未接入 FSRS 或 Anki。
4. 种子题库 30 道题，题量有限；覆盖不足时界面会明确提示，不会假装已掌握。
5. 题目配图字段已预留，但当前题库没有配图，界面不渲染图片。
6. 单用户本地模式，无账号与权限体系（数据库已保留 `user_id`）。
7. 在线 GenAI 已对学校真实端点做过连通与问答验收（`tools/e2e_online_school_check.py`，16 项），
   也覆盖了「配了在线却连不上」的回退路径（`tools/e2e_env_fallback_check.py`，11 项），
   并有 15 项 Mock 传输层单元测试（`tests/test_online_mode.py`）。
   未验证的是长期/高并发稳定性与 429 限流行为。
8. 视觉验收由具备图像输入能力的模型完成（`tools/vision_review.py`，10 张截图；
   `tools/vision_spotcheck.py`，图表与窄屏定向复核），
   结果见 `data/vision-review/vision-review.md`。
   执行本项目的模型本身不支持图像输入，这一步是委托给 `GLM-4.6V` 完成的。
8. 主观视觉评审未完成：执行本项目的模型不具备图像输入能力，
   无法“用眼睛看”截图；已完成的是真实浏览器 DOM 断言与像素级统计检查
   （详见 [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md) 第 6 节）。
   截图保留在 `data/ui-check/` 供人工查看。

---

## 教材参考说明

知识树结构参考了赵凯华《新概念物理教程》系列与曾谨言《量子力学教程》的**课程范围**，
仅用于确定知识点划分。**所有 30 道题均为原创**，不含教材原文、页码或例题编号，
也不包含任何未授权的扫描版内容。考试大纲需由你自行导入并核对来源。
