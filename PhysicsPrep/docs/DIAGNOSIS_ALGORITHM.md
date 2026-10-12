# 诊断算法说明

连续刷题增量：选择器增加先修证据不足惩罚；模式先改变候选目标再排序。
控制器保存补救→变式→返回目标状态，设置深度3与10分钟上限。
提示后正确和同日同模型重复正确不叠加正向掌握证据；普通练习不推迟待完成的到期复测。
只有无提示、到期且至少间隔一天的结果记为延迟独立复测。
文字/推导的结构化LLM意见仍为uncertain，不能提高掌握度。
详见[连续刷题说明](CONTINUOUS_PRACTICE.md)。下文公式仍用于有效判分证据，并非总作答次数。

本文给出第一版诊断算法的**完整、可测试**定义：掌握度估计、自适应选题、错因分析、
间隔复习与数学判分。代码位置：`physics_prep/diagnosis/`。

> **重要声明。** 这里是**启发式规则**，不是经过参数校准与效度检验的测量模型。
> 我们**不**把结果称为 BKT（贝叶斯知识追踪）或 IRT（项目反应理论）估计，
> 因为本项目没有标定数据集，也没有做过信度/效度分析。
> 界面与文档中所有“掌握度”都指本文件定义的启发式分数。

---

## 1. 掌握度估计

### 1.1 存储

按 `(user_id, topic_id)` 单独存储于 `mastery_records`，知识点定义本身不含掌握度。
每个知识点维护：

| 字段 | 含义 |
| --- | --- |
| `attempts` | 累计作答次数 |
| `correct` | 累计正确次数 |
| `recent` | 最近 7 次记录的 `{correct, difficulty}` 列表 |
| `estimate` | 掌握度估计，范围 `[0.05, 0.95]`，初始为 `NULL` |
| `last_practiced` | 最近练习时间 |

**初始值为 `NULL` 而不是 0 或 1**，表示“未知”。界面显示“未知（证据不足）”。
只有判分为 `correct` 或 `incorrect` 的提交才更新掌握度；`uncertain` 不更新。

### 1.2 公式

对某个知识点，设最近 7 次记录按时间升序为 $r_1 \dots r_n$（$n \le 7$，序号 $i$ 从 1 开始）：

**难度权重**（题目越难，做对的证据越强）：

$$ w_i = 1 + (d_i - 1) \times 0.12, \qquad d_i \in \{1,\dots,5\} $$

**近期加权表现**（越近的作答权重越大，线性递增）：

$$ R = \frac{\sum_{i=1}^{n} c_i \cdot w_i \cdot i}{\sum_{i=1}^{n} w_i \cdot i}, \qquad c_i = \begin{cases} 1 & \text{第 } i \text{ 次正确} \\ 0 & \text{否则} \end{cases} $$

**历史正确率的 Beta(2,2) 收缩**（少样本时向 0.5 收缩，等价于先验 2 次正确 + 2 次错误，
因此**一次答对不会被视为已掌握**）：

$$ H = \frac{\text{correct} + 2}{\text{attempts} + 4} $$

**最终估计**（历史占 70%，近期加权占 30%，再截断到 $[0.05, 0.95]$）：

$$ \text{estimate} = \mathrm{clamp}\bigl(0.7H + 0.3R,\ 0.05,\ 0.95\bigr) $$

`estimate` 保留 4 位小数。

### 1.3 行为示例（也是单元测试的断言依据）

| 情形 | 计算 | estimate |
| --- | --- | --- |
| 从未作答 | — | `NULL`（未知） |
| 1 次答对，难度 1 | $H=3/5=0.6$，$R=1$ | $0.42+0.3=0.72$ |
| 1 次答错，难度 1 | $H=2/5=0.4$，$R=0$ | $0.28$ |
| 2 次答对，难度 1 | $H=4/6\approx0.667$，$R\approx1$ | $\approx0.767$ |
| 4 次全对，难度 3 | $H=6/8=0.75$，$R=1$ | $\approx0.825$ |

可见单次作答的估计上限约为 0.72–0.78，需要多次、不同难度的正确作答才接近 0.95。
`tests/test_backend.py::test_public_snapshot_and_idempotency` 断言一次答对后
`estimate < 0.8`。

---

## 2. 自适应选题

`selector.select_question(questions, attempts, mastery, prerequisites, due)`

### 2.1 过滤

候选必须满足：`verified == True`、`source_type != 'official_exam'`、`frozen != True`。
未核验题与冻结模拟卷不会进入诊断。

在这批候选里，自适应诊断**只主动派发可确定性判分的题型**
（`AUTO_GRADED_TYPES` = 单选 / 多选 / 数值 / 符号）。原因：简答与推导题
（`short_answer`）在 `grade()` 里恒为 `uncertain`，既不更新掌握度，又占用一次
诊断名额——真实使用记录证实了这一点（一次三轮诊断里两轮拿到 `uncertain`，
用户无法从中得到任何信号）。开放题仍然保留：

- 通过「精确重做题目 ID」显式练习时不经过选择器，照常可用；
- 若过滤后候选为空（例如某个考点子集只有开放题），选择器退回未过滤的候选池，
  避免会话直接无题可做。

### 2.2 覆盖优先与重复控制

```text
未做过的题  ──有──► 只在这些题里选
      │
      无
      ▼
排除最近 3 次做过的题 ──有──► 在这些题里选
      │
      无
      ▼
排除与上一次完全相同的题
```

这保证：先铺开覆盖考点；题库耗尽后仍避免“连着出同一题”。

### 2.3 打分

对候选题 $q$，逐个关联知识点 $t$ 计算：

$$ \text{target}(t) = \mathrm{clamp}\bigl(\mathrm{round}(1 + 4\hat{m}_t),\ 1,\ 5\bigr) $$

其中 $\hat m_t$ 是该知识点掌握度（未知时取 1）。若**上一次答错且 $t$ 在补救集中**，
则 $\text{target} \mathrel{-}= 1$（**答错后降低难度**）。

$$ s(t) = v(t) + 2\cdot[t \in \text{due}] + 4\cdot[t \in \text{remedy}] - 7\cdot[t \in \text{repeated}] - 1.2\,|d_q - \text{target}(t)| $$

| 项 | 取值 | 作用 |
| --- | --- | --- |
| $v(t)$ | 未知 → 5；否则 $3(1-\hat m_t)$ | **优先覆盖尚未测试的考点**；薄弱考点权重更高 |
| due | +2 | 到期复习优先 |
| remedy | +4 | 上一次答错的考点**及其前置知识**优先 |
| repeated | −7 | 最近 3 次都练同一考点时，抑制继续叠加 |
| 难度差 | −1.2 / 级 | 让题目难度靠近当前目标难度 |

题目得分取所有关联知识点得分的**最大值**，排序键为 `(得分, -难度, id)`，
即同分时优先简单题、再按 ID 稳定排序（保证结果可复现）。

选择的题目会附带 `recommendation_reason`（如“错误后补救或前置知识；未测试考点”），
界面直接显示，做到**可解释**。

### 2.4 防止无限循环

- 未做题优先 ⇒ 不会在单一薄弱点反复出题；
- `repeated` 惩罚 ⇒ 连续同一考点会被压制；
- 全部候选都被排除时返回 `None`，会话标记为 `completed`，界面提示本轮完成，
  而不是伪造一道题。

### 2.5 题库覆盖不足

当 `select_question` 返回 `None` 或候选数很少时，`report()` 会在诊断报告中附带
`coverage_notice`：“仅反映本次有限样本，题库覆盖不足或未知考点不可据此认定掌握。”
界面在答题页显示“选题理由”，在报告页显示该提示。

---

## 3. 错因分析

### 3.1 类别

`diagnosis/engine.py` 定义 9 个类别：

`概念理解错误`、`公式使用错误`、`物理模型建立错误`、`受力 / 几何分析错误`、
`数学计算错误`、`单位和量纲错误`、`审题错误`、`知识缺失`、`尚无法确定`

### 3.2 当前实现与不确定性

| 判分结果 | 记录的 `error_category` | 说明 |
| --- | --- | --- |
| `correct` | `无` | 提示“仍需其他题与延迟复测确认” |
| `uncertain` | `尚无法确定` | 提示检查表达式或人工复核 |
| `incorrect` | `尚无法确定` | 提示“仅凭最终答案不能可靠识别错因” |

**为什么答错时默认是“尚无法确定”**：学生只提交一个选项或一个最终表达式时，
正确与错误之间存在多种可能路径（概念、模型、受力分析、代数、单位、审题），
仅凭最终答案**无法**可靠区分。把猜测写成确定结论会误导复习方向。

因此系统采取的策略是：

1. 记录确定性判分结果，并明确标注错因“尚无法确定”；
2. 通过选题算法安排**前置知识点的追问题**，用后续证据逐步收敛；
3. 大模型只能给出**建议性**措辞（`llm/prompts.py::ERROR_ANALYSIS_PROMPT` 要求
   使用“可能”“建议核实”，并说明还需要问学生什么）；
4. 模型意见**不写入** `error_category`，不影响掌握度与判分。

`uncertain` 的作答不计入掌握度更新，也不计入正确率分母（`report()` 单独统计 `uncertain` 数）。

---

## 4. 间隔复习

第一版是轻量规则（`mastery.update_mastery` 的返回值）：

| 条件 | 间隔 |
| --- | --- |
| 答错 | 1 天 |
| 答对且最近连续正确次数 < 2 | 3 天 |
| 答对且连续正确 2–3 次 | 7 天 |
| 答对且连续正确 ≥ 4 次 | 14 天 |

连续正确次数由 `recent` 从末尾向前数得到。`due_at = now + interval`，
写入 `review_schedule`。到期考点在选题时获得 +2 权重，并显示在“到期复习”列表。

> 这不是 FSRS / SM-2 等经过大规模数据校准的算法，只是可解释的启发式安排。
> 后续可替换为 FSRS，不影响其余模块。

---

## 5. 数学判分（`math_grader.py`）

### 5.1 输入约束

| 约束 | 值 | 目的 |
| --- | --- | --- |
| 输入长度 | ≤ 300 字符 | 防止构造超大表达式 |
| AST 节点数 | ≤ 100 | 限制复杂度 |
| 嵌套深度 | ≤ 15 | 防止递归爆炸 |
| 数值字面量 | ≤ 1e12 | 防止天文数字 |
| 幂指数 | 必须是无自由符号、$|x| \le 20$ 的实常量 | 直接拒绝 `2**100000` |
| 符号名 | `[A-Za-z][A-Za-z0-9_]{0,20}`，最多 20 个 | 由题目 `allowed_symbols` 给出，缺省时从标准答案提取 |
| 函数 | `sqrt sin cos tan exp log abs` | 白名单 |
| 运算 | `+ - * / **`（`^` 自动转为 `**`） | 无属性访问、无下标、无推导式、无 lambda |

解析使用 `ast.parse(mode='eval')` + 手写白名单遍历。
**不使用 `eval`，也不使用 SymPy 的 `parse_expr`**（后者会引入隐式函数与自动符号，
并且历史上存在解析层风险）。

### 5.2 判定顺序

```text
1. 结构完全相同            → correct
2. difference.is_zero      → correct
3. 含浮点数或数值题        → 数值容差比较（默认 1e-6 相对容差）
4. together → cancel → simplify 后为 0 → correct
5. 仍有自由符号            → 正有理数代入找反例
      找到反例            → incorrect
      未找到              → uncertain
6. 无自由符号且不为 0      → incorrect（仅数值题）
```

第 5 步**只用于证明“不等价”**：抽样一致永远不能证明等价，因此不构成 `correct` 的依据。

### 5.3 超时与失败

每个昂贵步骤前后检查墙钟截止时间（默认 5 秒，`grading_timeout` 可覆盖）。
超时或任何解析失败 → `uncertain`，附带可操作提示（检查显式乘号、符号白名单、定义域）。

早期实现用 `multiprocessing` 子进程实现硬超时；该方案依赖命名管道，
在受限环境下会导致**全部判分不可用**，现已改为纯进程内实现。

### 5.4 单位与量纲

`units.py` 只识别**明确写出的单位**：

- `m/s`、`kg*m/s**2` 这类复合单位可按组成部分整体识别；
- 单字母（`m`、`s`、`N`…）有歧义，只有题目声明了 `expected_unit` 时才当作单位；
- 含下划线的符号（`epsilon_0`）**不**当作单位；
- 若题目声明 `expected_unit` 而作答单位不符 → 返回 `uncertain` 并提示核对，
  **不直接判错**（避免符号名误伤）。

### 5.5 判分权威性

判分结果完全由上述确定性流程决定。大模型输出不参与判分，
`grade()` 的返回值是掌握度与学习记录的唯一依据。

---

## 6. 可测试性

上述每条规则都有对应测试：

| 规则 | 测试 |
| --- | --- |
| 掌握度公式与“一次答对不算掌握” | `tests/test_backend.py::test_public_snapshot_and_idempotency` |
| 选题补救优先、避免循环 | `tests/test_backend.py::test_selector_remedy_coverage_and_no_loop`、`tests/test_acceptance.py::test_scenario_b_selector_prefers_remedy_and_avoids_loop` |
| 答错后降难度与安排复习 | `tests/test_acceptance.py::test_scenario_b_error_remedy` |
| 表达式等价（含 `M*g*sin(theta)/(M+M/2)` vs `2*g*sin(theta)/3`） | `tests/test_seed_grading.py::test_rolling_alternative_form_and_positive_domain` |
| 30 道种子题标准答案自判为 correct | `tests/test_seed_grading.py::test_all_verified_objective_seeds_grade_their_standard_answers` |
| 非法/攻击表达式返回 uncertain | `tests/test_seed_grading.py::test_untrusted_expression_syntax_returns_uncertain`、`tests/test_math_llm.py::test_unsafe` |
| 超时返回 uncertain | `tests/test_math_llm.py::test_numeric_and_uncertain` |
| 单位不符返回 uncertain | `tests/test_ui_views.py::test_unit_mismatch_returns_uncertain_not_incorrect` |
| `uncertain` 不更新掌握度 | `tests/test_backend.py`（`certain` 过滤）与 `test_acceptance.py` |
