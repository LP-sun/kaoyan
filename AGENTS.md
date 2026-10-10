# AGENTS.md

本文件为在工作区 `考研专业课/` 中接续工作的 Agent 提供指导说明。
学习者请先读 [README.md](README.md)；写题与改题库再读 [题库写作指南](题库写作指南.md)。

## 工作区概述

中国硕士入学考试物理专业课（651 普通物理、803 量子力学）的备考工作区，含四块彼此独立的内容：

| 目录 | 性质 | 技术栈 |
| --- | --- | --- |
| `资料整理/` | 教材习题提取、相关性初筛、推荐引擎、离线题库网页 | Python + 原生 JS（无构建步骤） |
| `PhysicsPrep/` | 本地自适应诊断学习平台 | Python 3.11+ / Gradio / SQLAlchemy / SQLite |
| `fastgpt-physics-lab/` | FastGPT 部署包 + Node 诊断工作流 | Node ESM（零第三方依赖）+ Docker Compose |
| `教材/`、`允文君数学物理资料分享/`、根目录 `*.pdf` | 用户自备原始资料 | **只读**，不要改名或覆盖 |

后两者是**同一台机器上并行开展的两个实验**，刻意互相隔离，不要合并数据或共用数据库。

## 必须先知道的现状

写代码之前先确认你要动的是"数据管道"还是"内容"，这两者进度完全不同：

- **数据与工程已基本完成**；**人工内容核验进度为 0**。截至 2026-10-10：
  - `资料整理/题库/教材习题.json` 2,007 条记录，其中 **0 条**有解析（`answer` 字段全空）、**0 条**标注了难度（全部"未评定"）、**0 条**状态为已核验。
  - `资料整理/题库/相关性人工修订.json` **不存在**，即尚无任何人工复核结论落盘。
  - `资料整理/题库/写作/` 目录**已建立**（含示例与校验脚本），但除示例外**尚无人工核验记录**，无一条解析落盘。
  - 651 分层：大纲候选 1,211 / 概念了解 128 / 待核 668。803 分层：大纲候选 184 / 待核 1,823。
- **逐题题型分类已完成**（`资料整理/题库/deepseek相关性分析.json`，2,007 条）：定量计算 1,062 / 开放论述 364 / 概念判断 260 / 推导证明 229 / 综合应用 90 / 公式辨析 2；其中**可自动判分 1,324 条**。参数见 `推荐参数v3.json`。
- **DeepSeek 相关性分析已完成**：`deepseek相关性分析.json` 全部 2,007 条含 `relevance`（上海科大网关 + `deepseek-pro`）。**模型判断，非人工核验**：high 551 / medium 934 / low 437 / none 85；平均 60.7 分；651 命中 1,747、803 命中 267。汇总见 `资料整理/题库/相关性评估报告.md`。Keyword 初筛结果另存于 `考研相关性.json`，由推荐引擎消费。
- **模型相关性已接入推荐**：`分析考研相关性.py` 只读合并 `relevance` 进 `考研相关性.json`；`推荐引擎v2.js` 按级别微调分数（high +14 / medium +4 / low −10 / none −30）并按 `exam_fit` 惩罚；推荐页有「相关性下限」筛选。`推荐参数v3.json` **未被引擎消费**，仅作设计参考。
- 当前**可直接练习的题只有 89 道**：基础题 49（`资料整理/`）+ PhysicsPrep 种子 30 + fastgpt-lab 题库 10。
- "题面已提取" ≠ "题面已核验" ≠ "题型已分类" ≠ "相似度/相关性已评估" ≠ "解析已完成" ≠ "已接入网页"。**这些状态必须分开表述，不得合并成一个"完成"。**

## 常用命令

Python（`资料整理/` 的脚本依赖该目录内的 `工具依赖/`，在其中直接运行）：

```bash
python 资料整理/分析考研相关性.py      # 重跑逐题相关性初筛，保留人工修订
python 资料整理/构建教材题库.py        # 重新生成聚合 JSON/CSV/数据 JS 与离线网页（含合并 写作/ 目录）
python 资料整理/验证教材题库.py        # 校验题库路径、图片、编号
python 资料整理/题库/校验写作.py       # 校验 写作/ 人工记录的结构与状态一致性（只读）
```

题型分类与推荐参数（`资料整理/题库/构建题库与推荐.py`）：

```bash
python 资料整理/题库/构建题库与推荐.py            # 只做本地确定性分类，生成 deepseek相关性分析.json（保留既有 relevance）
python 资料整理/题库/构建题库与推荐.py --deepseek --resume   # 调用模型逐题评估相关性（密钥只从环境变量读）
python 资料整理/题库/汇总相关性评估.py         # 汇总 relevance 为人读报告（相关性评估报告.md）
```

> 密钥变量：`DEEPSEEK_API_KEY` 或 `GENAI_API_KEY`；端点 `DEEPSEEK_BASE_URL`；模型 `DEEPSEEK_MODEL`。
> 上海科大网关实测：`DEEPSEEK_BASE_URL=https://genaiapi.shanghaitech.edu.cn/api/v1/start`、
> `DEEPSEEK_MODEL=deepseek-pro`，脚本会自动补 `/chat/completions`（该端点带与不带后缀均 200）。
> 凭据在桌面 `genai/genai_keys.json`，**不要**写入仓库或贴入聊天。脚本已设 `max_tokens=4000`，
> 避免推理型模型思维链吃光预算导致 JSON 截断。

推荐引擎与题库网页为纯 JS：

```bash
node 资料整理/题库/测试推荐引擎.js     # 3 组断言；不写浏览器学习记录
```

PhysicsPrep（需其自带虚拟环境）：

```bash
PhysicsPrep\.venv\Scripts\python.exe -m pytest    # 当前 133 passed
PhysicsPrep\.venv\Scripts\python.exe app.py       # http://127.0.0.1:7860
```

fastgpt-physics-lab：

```bash
node fastgpt-physics-lab/tools/validate-bank.mjs   # 12 项
node fastgpt-physics-lab/tools/physics-checks.mjs  # 10 项
node fastgpt-physics-lab/tools/e2e-test.mjs        # 45 项，需先启动诊断服务
```

## 关键约束

1. **不要重跑 `资料整理/制作题库.py`**。它会覆盖手工修改过的页面。改动题库请走 `构建教材题库.py`。
2. **人工写作只写新文件**：`资料整理/题库/写作/<教材ID>/<题目ID>.json`，一题一文件，UTF-8，格式与状态字段见 [题库写作指南](题库写作指南.md)。生成器与聚合文件（`教材习题.json`、`教材题库数据.js` 等）由单一负责人修改，不要手改产物。
3. **题目 ID 是稳定标识**，形如 `BK04-思考题-6-11`，必须原样保留，不要重编号或去重。
4. **不得虚构内容**：题号断号保留原样（力学第 3 章 3-21 直接跳 3-23，原书如此）；看不清的题面记为疑点，不按 OCR 猜写；不伪造难度、耗时、真题频率等未测数据。
5. **电磁学答案资料是第三版**，不可按题号直接配给第二版题目。两个量子物理版本分别整理，**不做跨版去重**。BK09《量子力学教程》是单页 DRM 提示文件，不是可用教材。
6. **不要修改浏览器学习记录**（`physics-records-v1`），也不要改写 `fastgpt-physics-lab/data/diagnosis-sessions.json` 做测试。
7. **三份真题（23普物、24普物、24量子）默认冻结为模拟卷**，不得进入自动推荐器，只能由学习者主动解冻后限时使用。
8. 密钥只存在于 `PhysicsPrep/.env` 与 `fastgpt-physics-lab/env/.env`（均已 gitignore）。**不要**外发、贴入聊天或提交；脚本输出中只显示长度与末四位。
9. 两个项目共享 `fastgpt-physics-lab/env/.env` 的凭据：PhysicsPrep 的 `verify_with_lab_env.py` 等只读该文件。**不要删除或移动它**，否则打断对方在线验证；轮换 key 需两边协调。
10. `fastgpt-physics-lab` 的 Compose 项目名已固定在其 `docker-compose.yml` 顶层 `name:`。**严禁** `docker system prune`、`docker volume prune` 或不带项目限定的批量停止。

## 环境事实（本机实测，勿凭通用经验推断）

- **无 Docker daemon**：`docker` CLI 存在但 `dockerDesktopLinuxEngine` 管道不存在。FastGPT 全栈当前**未在运行**；要用需先启动 Docker Desktop。
- **沙箱禁止删除目录**：pytest 在受限沙箱下报 `PermissionError: [WinError 5]`，失败点是 `shutil.rmtree` → `os.rmdir`，即临时目录**建得出、删不掉**。`--basetemp=<工作区目录>` **不能**绕过它。完整分析见 `PhysicsPrep/docs/TEST_REPORT.md` 的"关于测试临时目录"。工作区内遗留的 `.pytest_tmp`、`.test_core*`、`.test_progress*` 即此机制产物，删不掉属正常。
- **`curl` 无法建立 TLS**（沙箱不开放证书存储，`SEC_E_NO_CREDENTIALS`）。抓网络请用 **Node 内置 `fetch`**；`git` 需显式切 OpenSSL 后端。
- **端口 3100 可用**（早期"被禁用"的结论已被 15 次重复 bind 实测推翻）。3100 FastGPT Web、3101 本地诊断、3102 sandbox 代理，全部只绑 `127.0.0.1`。
- **上海科大 GenAI 网关可用**，Base URL 必须填到 `/api/v1/start`（SDK 自动补 `/chat/completions`）；它**不提供 embeddings 接口**，故 `GENAI_EMBEDDING_MODEL` 留空，知识库不可用。生效配置为并行科技。
- 调用会先输出思维链并计入 completion tokens：**`max_tokens` 必须 ≥ 2500**，否则 JSON 被截断，会被误判为"模型不会输出合法 JSON"。

## 提交前自检

- 改了题库数据 → 跑 `验证教材题库.py`，并抽查离线网页中题面、原页跳转、跨页题。
- 改了或新增 `写作/` 记录 → 先跑 `资料整理/题库/校验写作.py`，再跑 `构建教材题库.py`，并抽查网页中解析折叠、状态徽标与来源跳转。
- 改了推荐逻辑 → 跑 `测试推荐引擎.js`。
- 改了 PhysicsPrep → 跑 `pytest`（无沙箱限制时）与 `tools/preflight_check.py`。
- 改了 fastgpt-lab 题库 → 跑 `validate-bank.mjs`、`physics-checks.mjs`，再 `node tools/export-bank.mjs` 重新生成派生文件。
- 文档中的数字（题量、通过率、覆盖数）必须实测后再写，且注明口径。

## 已知未完成项

- `题库写作指南.md` 的人工写作格式**已接入构建器与网页**（`构建教材题库.py` 合并 `写作/` 目录；网页渲染题面与折叠解析）。但 `写作/` 下**尚无已核验记录**，尚无一条解析落盘；接入后仍需在实际网页抽查公式、图示、跨页题与来源跳转。
- 公式 OCR、逐题裁图边界、解答与题面对应关系均需逐题核验。
- PhysicsPrep 与 fastgpt-lab 各自独立，**尚无共用题库**；教材题库 2,007 题也未导入任一平台。
- 大纲覆盖缺口看板：见 `资料整理/大纲教材对应表.md`，其中"章号未核实"仍待核。
