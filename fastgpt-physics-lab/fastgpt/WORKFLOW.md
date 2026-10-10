# 物理考研智能诊断 — FastGPT 工作流搭建规格（v4.17.x）

应用名称：`Physics Diagnostic Tutor`
中文显示名：`物理考研智能诊断`

> 本文档中所有节点类型名、输入输出字段名，均已对 **FastGPT v4.17.0 源码**核验
> （`packages/global/core/workflow/node/constant.ts` 与
> `packages/global/core/workflow/template/system/interactive/*.ts` @ tag `v4.17.1`）。

---

## 0. 先决条件

| 项目 | 要求 | 本项目状态 |
| --- | --- | --- |
| Docker Engine + Compose v2 | 必需 | **本机未安装**（见部署报告"已知限制"） |
| FastGPT 版本 | v4.17.0（镜像 `fastgpt:v4.17.0`） | 已固定版本 |
| 语言模型 | 通过「模型提供商」配置一个 OpenAI 兼容渠道 | 待用户填入 GenAI 参数 |
| 索引模型（Embedding） | 仅知识库向量检索需要 | 学校未提供时为不可用，**不影响本工作流** |
| 系统插件 | 本工作流**不需要**额外插件 | — |

---

## 1. 与你可能看到的旧教程的差异（重要）

1. **模型不再通过 `OPENAI_BASE_URL` / `CHAT_API_KEY` 环境变量配置。**
   v4.17 的模型配置在 **管理界面 → 账号 → 模型提供商** 中完成，
   数据存在 MongoDB 里；仅改环境变量不会生效。
2. v4.17 的部署模板**自带 `fastgpt-plugin` 服务**，官方文档把「系统插件」列为必需组件；
   v4.14 及更早没有这一项。
3. 官方 Compose 模板默认把 `fastgpt-app` 映射到 `3000:3000`，
   **并且所有内部服务默认带固定 `container_name`**（如 `fastgpt-mongo`）。
   本项目为了隔离，已删除全部 `container_name`（见 `docker-compose.yml` 顶部注释）。
4. 旧教程中的 `STORAGE_EXTERNAL_ENDPOINT`（S3 地址）只对 v4.14 及更早的模板有意义，
   v4.17 默认 `STORAGE_DOWNLOAD_URL_MODE=short-proxy`，不需要额外 S3 地址。

---

## 2. 已核验的原生交互节点

| 节点 | `flowNodeType` | 关键输入 | 关键输出 | 说明 |
| --- | --- | --- | --- | --- |
| 用户选择 | `userSelect` | `description`（说明文字）、`userSelectOptions`（选项数组，每项 `{key,value}`） | `selectResult`（string） | 前端渲染成**可点击选项** |
| 表单输入 | `formInput` | `description`、`userInputForms`（字段定义数组） | `formInputResult`（object，按字段 key 取值） | 前端渲染成**表单**（文本框/数字/选择等） |
| 条件判断 | `ifElseNode` | 多个条件分支 | 各分支输出 | 用于判分分支 |
| 指定回复 | `answerNode` | 文本 | — | 输出给用户的文本 |
| AI 对话 | `chatNode` | 模型、提示词、消息数组 | 模型回答 | 调用语言模型 |
| HTTP 请求 | `httpRequest468` | 方法、URL、头、体 | 响应体 | **本工作流未使用**（判分不需要外部调用） |
| 循环 | `loop` / `loopStart` / `loopEnd` | 数组、循环体 | 各轮结果 | 用于"逐题循环" |
| 代码运行 | `code` | 代码、输入 | 输出字段 | 用于取题与判分 |
| 全局变量 | `Workflow Variables` | — | — | 保存跨轮状态 |

> 交互节点的判定集合在源码中为 `INTERACTIVE_NODE_TYPES = {userSelect, formInput}`。
> 二者都是**阻塞式**节点：执行到此处会暂停工作流，把交互下发给前端，
> 收到用户提交后继续。因此**逐题流程必须用它们来"等学生作答"**。

---

## 3. 工作流拓扑

```
[流程开始]
   │  输入：subject(字符串)、chapter(字符串)
   ▼
[A userSelect] 选择科目          → selectResult ▼
[B userSelect] 选择章节          → selectResult ▼
   ▼
[Loop 开始]  循环数组 = 题型选择器（由 C 节点生成）
   │  循环变量：qIndex(数字,从0)、records(数组,空)
   ▼  ←──────────────────────────────────────────────┐
[C code]  从题库取 questions[qIndex]，输出：        │
       qId / stem / optionA..D / correctKey / explanation / isLast
   ▼                                                │
[D answerNode]  展示题干与四个选项（含公式）          │
   ▼                                                │
[E userSelect]  "请选择你的答案"                    │
       选项 userSelectOptions =                         │
         [{key:'A',value:'A'},{key:'B',value:'B'},      │
          {key:'C',value:'C'},{key:'D',value:'D'}]      │
   ▼                                                │
[F ifElseNode]  selectResult == correctKey ?          │
   ├── true  ──► [G1 answerNode] "回答正确 + 解析"     │
   └── false ──► [G2 chatNode]   错因分析（见 §5）     │
                 （输出严格 JSON，可能误区 + 置信度）  │
   ▼                                                │
[H code]  把 {qId, chosen, correct} 追加进 records   │
   ▼                                                │
[I formInput] "是否继续下一题？"                      │
       字段：continue（选择型：继续 / 结束）          │
       取值必须写 {{I.formInputResult.continue}}     │
       （formInput 输出是 object，写 {{I.continue}} 取不到值）
   ▼                                                │
[J ifElseNode]  formInputResult.continue == "stop"    │
                或 isLast == true ?                    │
   ├── 否 ──► 回到 [C]（Loop 下一轮）────────────────┘
   └── 是 ──► [K code] 汇总统计（确定性，不用模型）
                │  正确题数 / 总题数 / 覆盖章节 /
                │  已确认薄弱 / 疑似薄弱 / 下一组练习
                ▼
              [M chatNode] 学习建议（见 §7）
                ▼
              [L answerNode] 输出诊断报告（见 §8）
                ▼
              [流程结束]
```

> **节点编号说明**：`[K]` 是**统计 code 节点**，报告里的每个数字都来自它，
> 因此报告可复现、不受模型影响；`[M]` 才是学习建议的模型节点。
> 原稿把统计与建议混在同一个 `[K]`，会导致报告引用了没有任何节点产出的变量
> （已由 `tools/workflow-check.mjs` 的跨节点引用检查抓出并修正）。

---

## 4. 关键实现要点（避免踩坑）

1. **公式显示**：题干与选项用 LaTeX 书写（`$...$` 行内、`$$...$$` 独立行）。
   FastGPT 前端使用 KaTeX 渲染 Markdown 中的数学公式。
   *本项目本地实现已内置 KaTeX（`third_party/katex`），FastGPT 端无需额外配置。*
2. **正确答案不能提前显示**：`[D]` 节点只输出 `stem` 与 `optionA..D`；
   `correctKey`、`explanation` 必须**只在 `[F]`（判分）之后**的节点中引用。
   如果把它们拼进 `[D]` 的文本里，答案就会提前泄露。
   > 蓝图用 `phase: "pre-submit" | "post-submit"` 把这件事显式标注出来，
   > 并由 `tools/workflow-check.mjs` **强制检查**：`phase=pre-submit` 的节点
   > 只要出现 `correctKey` / `explanation` / `commonMisconceptions` 就直接判失败。
   > 这样以后改提示词时不会不小心把答案挪到提交前。
3. **不要把判分交给模型**：`[F]` 的分支条件用
   `selectResult == correctKey` 做**字符串相等比较**，`correctKey` 来自固定题库。
   模型只参与 `[G2]` 的错因分析和 `[M]` 的学习建议。
   > `[H]` code 节点也会做一次同样的字符串比较（产出 `wasCorrect`）供统计使用，
   > 与 `[F]` 保持同一判据，不存在"两套标准"。
4. **状态不串题**：`records` 必须由 `[H]` 显式更新，`chosen` 每轮从 `[E].selectResult` 重新读取。
   不要用"全局变量"存上一题的选择，否则下一题会错误保留上一次选择。
5. **可随时停止**：`[I]` 提供"结束"选项；也可以在聊天输入框发送任意消息，
   FastGPT 会中断当前交互节点（此时应把 `records` 作为报告输入，允许提前结束）。
6. **报告数字必须来自 code 节点**：`[K]` 用与 `tools/diagnosis-server.mjs`
   的 `ruleBasedReport()` **完全相同**的阈值规则计算统计量，
   再由 `[L]` 引用。不要把这些数字交给模型生成——那会每次都不一样、无法复现。
7. **题库导入方式二选一**：
   - 方式 A（推荐，无需知识库）：把 `bank/questions.json` 的内容转成一个
     `[C] code` 节点里的常量数组，或放进「工作流变量」的字符串里。
     10 道题体积很小，不触碰 Embedding 配额，也不需要向量库。
   - 方式 B：建知识库 + 用「知识库搜索」节点。
     **该方式需要 Embedding 模型**；学校 GenAI 未提供 Embedding 时不可用。
   - 本题库的第一版**采用方式 A**，因此工作流不依赖向量检索。

---

## 5. `[G2]` 错因分析节点提示词（可直接复制）

**模型参数**：温度 0.2，**最大回复长度 ≥ 2500**。

> ⚠️ **最大回复长度不要设小**（原文档写 700，已实测证明会导致故障）。
> 原因：`DeepSeek-V4-Flash`、`GLM-5.3` 等模型会先输出思维链
> （`reasoning_content`），而**思维链同样计入回复长度配额**。
> 配额被思维链吃光后，正式 JSON 一个 token 都分不到，
> `finish_reason` 变成 `length`，表现为「模型返回的不是可解析 JSON」——
> 很容易被误判成模型能力不足。实测 700 时空文本/半截 JSON，2500 以上稳定正常。
> 同一个坑也发生在本地工具里，已一并修复（见 `FASTGPT_DEPLOY_REPORT.md` §9.2）。

**系统提示词**：

```
你是一位普通物理力学助教，正在分析一名考研学生的选择题作答记录。

严格要求（必须遵守）：
1. 你只能看到学生选择的选项，看不到他的草稿或推理过程。
2. 因此你绝不能断言学生"就是"犯了某个具体错误，只能提出"可能的误区"。
3. 若仅凭一次选错无法区分原因，你必须在 follow_up_question 字段给出一道能区分不同原因的追问。
4. 不要输出解题全过程，只输出诊断信息。
5. 只输出一个 JSON 对象，不要输出 markdown 代码块或任何额外文字。

JSON 结构：
{
  "topic": "知识点名称",
  "correct": true/false,
  "possible_misconceptions": ["可能的误区1", "可能的误区2"],
  "confidence": "low" | "medium" | "high",
  "recommended_review": ["需要复习的具体内容"],
  "follow_up_question": "用于区分上述误区的一道追问（若无必要则填空字符串）"
}
```

**用户提示词**：

```
题目（知识点：{{chapter}} / {{knowledgePoints}}，难度：{{difficulty}}）
{{stem}}

选项：
A. {{optionA}}
B. {{optionB}}
C. {{optionC}}
D. {{optionD}}

学生的作答：{{selectResult}}
标准答案：{{correctKey}}

标准解析（供你判断学生可能卡在哪一步，不要复述给学生）：
{{explanation}}

请按系统提示的 JSON 结构输出诊断。
```

> **为什么必须强调"可能"**：只拿到一个错误选项时，无法区分是概念错误、公式误用、
> 前置知识缺失还是计算失误。把它们写成确定性诊断就是编造证据。

---

## 6. `[K]` 汇总统计节点（code，确定性，不调用模型）

`[L]` 报告里的**每一个数字**都来自这个节点。规则与
`tools/diagnosis-server.mjs` 的 `ruleBasedReport()` **完全一致**，
因此报告可复现、可审计，不会因为模型随机性而每次不同。

**输入**（code 节点的输入）：`records`
（数组，每项形如 `{qId, chapter, chosen, correct}`）

**输出**：

| 输出键 | 类型 | 含义 |
| --- | --- | --- |
| `answeredCount` | number | 已作答题数 |
| `correctCount` | number | 答对题数 |
| `testedChapters` | string | 本次覆盖的章节，去重后用 `、` 连接 |
| `confirmedWeakAreas` | string | **已确认薄弱**章节 |
| `suspectedWeakAreas` | string | **疑似薄弱**章节 |
| `nextPractice` | string | 下一组练习建议（按薄弱程度排序取前 2 个章节） |

**判定阈值（与本地实现一致，务必不要改）**：

```
按章节分组统计作答数 asked 与错题数 wrong：

已确认薄弱（confirmed）：wrong >= 2
                        或 (asked >= 2 且 wrong / asked >= 0.5)
疑似薄弱（suspected）：wrong >= 1 但未达到上面的已确认阈值
```

**为什么阈值必须是 `asked >= 2`**：只错 1 题不足以判定一个章节薄弱，
更不能从单个错选项反推具体误区。这个下限就是"不编造证据"的落实。

**输出必须是字符串而非数组**：`answerNode` 的文本里用 `{{K.confirmedWeakAreas}}`
插值，数组会被渲染成难读的形式；`[K]` 内部负责拼成中文串
（例如 `刚体转动（错 2/3）`），没有薄弱项时输出 `（本次未发现）`。

---

## 7. `[M]` 学习建议节点提示词（可直接复制）

**模型参数**：温度 0.3，**最大回复长度 ≥ 2500**（理由同 §5 的说明：思维链占用配额）。

**系统提示词**：

```
你是一位考研物理辅导老师。学生会给你一份本次诊断的作答汇总（每题的知识点、对错、
以及基于选择题无法确定的可能误区）与已算好的统计量。

要求：
1. 只依据给出的汇总与统计量，不要假设学生未表现出的问题。
2. 明确指出哪些薄弱环节是"可以确认的"（多次出错/相关知识点连续出错），
   哪些只是"疑似"（仅一次出错，证据不足）。
3. 给出 3 条以内的具体复习建议与一组下一步练习方向。
4. 用简洁中文，分点输出，不超过 350 字。不要输出 JSON。
5. 不要自己重新计算正确率；统计量已由工作流给出，直接引用即可。
```

**用户提示词**：

```
本次作答汇总：
{{records}}

统计：答对 {{K.correctCount}} / {{K.answeredCount}}，已确认薄弱：{{K.confirmedWeakAreas}}，疑似薄弱：{{K.suspectedWeakAreas}}

请按上述要求给出学习建议。
```

**输出**：`answerText`，由 `[L]` 报告节点引用为 `{{M.answerText}}`。

---

## 8. `[L]` 诊断报告输出结构

报告分两部分：**统计部分**（由 `[K]` code 节点按规则计算，保证确定性）+
**建议部分**（`[M]` 模型生成）。

```json
{
  "total": 5,
  "correctCount": 3,
  "accuracy": 0.6,
  "testedChapters": ["刚体转动", "纯滚动"],
  "confirmedWeakAreas": [
    { "chapter": "刚体转动", "wrong": 2, "asked": 3, "wrongIds": ["MECH-RB-002", "MECH-RB-003"] }
  ],
  "suspectedWeakAreas": [
    { "chapter": "纯滚动", "wrong": 1, "asked": 2, "wrongIds": ["MECH-RL-001"] }
  ],
  "nextPractice": [
    { "chapter": "刚体转动", "suggestedQuestionIds": ["MECH-RB-001"] }
  ],
  "llmAdvice": "（模型生成的中文复习建议，≤350 字）",
  "caveat": "以上薄弱环节是基于选择题对错的推断，不是确定诊断结论。"
}
```

判定规则（与本地实现 `tools/diagnosis-server.mjs` 的 `ruleBasedReport()` 完全一致）：

- **已确认薄弱**：同一章节错误 ≥ 2 题，**或**该章节错误率 ≥ 50% 且至少答了 2 题；
- **疑似薄弱**：该章节有错但未达到上面的阈值。

---

## 9. 长期学习记录的正确做法

FastGPT 的**聊天历史不等于学生能力数据库**。本工作流第一版只使用：

- 工作流变量（单次会话内）；
- 会话记录（用于生成当次报告）。

如果需要跨会话的掌握度追踪，应**另外**接一个独立数据库，
并且**不得复用 PhysicsPrep 的 SQLite 文件**。
本次交付未做该扩展；如需，可基于本项目的 `data/diagnosis-sessions.json`
（本地实现已落盘，结构与 FastGPT 的 records 一致）另建库。

---

## 10. 手动搭建步骤（约 20 分钟）

1. 浏览器打开 `http://127.0.0.1:3100`，用 `root` + `env/.env` 里的 `DEFAULT_ROOT_PSW` 登录。
2. **账号 → 模型提供商 → 添加渠道**：
   - 类型选 OpenAI 兼容（自定义）；
   - 接口地址填 `GENAI_BASE_URL`（本机若开了代理，注意容器内访问不到 `127.0.0.1`，
     此时应填学校网关的真实域名，不要填本机回环地址）；
   - Key 填学校提供的值；
   - 模型 ID 填 `GENAI_MODEL`；把该模型同时勾选为「语言模型」；
     若学校提供 Embedding 才勾「索引模型」。
3. **工作台 → 新建应用 → 高级编排**（界面里也可能显示为「工作流应用」），
   命名 `Physics Diagnostic Tutor`，显示名 `物理考研智能诊断`。

   > 实测提示（本轮从接口的 zod 校验里确认）：应用类型枚举是
   > `folder | toolFolder | simple | chatAgent | advanced | plugin | toolSet | httpToolSet | hidden | tool | httpPlugin…`，
   > **其中没有 `workflow` 这个值**。高级编排应用在接口层对应的是 **`advanced`**，
   > 而 `simple` 是简易对话应用。别在界面里找 `workflow` 而以为功能缺失。
4. 按 §3 的拓扑拖出节点，按 §5/§7 粘贴提示词，按 §6 实现统计 code 节点，
   把 §4 的要点逐条落实。
5. **务必搭出 `[K]` 统计 code 节点**：`[L]` 报告里的所有数字都由它产出。
   漏掉它会让报告里出现空值（`tools/workflow-check.mjs` 的跨节点引用检查就是为了
   防止这种「引用了不存在的输出」）。
6. 点右上角「运行」做一次完整测试：
   选「力学」→「刚体转动」→ 点一个错误选项 → 看是否出现"可能误区"而不是断言 → 继续 → 结束看报告。
7. 保存并发布。

> 本项目的本地实现（`tools/diagnosis-server.mjs`）与这条工作流是**同一套规则**的两种落地：
> 本地版已通过 45 项端到端测试。搭建 FastGPT 端时可拿它当参照物逐项对照。

> 命令行核对模型配置是否生效：
> ```bash
> docker compose --env-file env/.env -p fastgpt-physics-lab exec fastgpt-app \
>   node -e "fetch('http://127.0.0.1:3000/api/common/system/getInitData').then(r=>r.json()).then(j=>console.log(JSON.stringify(j).slice(0,400)))"
> ```
> 更可靠的方式仍是直接在界面里发一条测试消息。
