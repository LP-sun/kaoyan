# fastgpt-physics-lab

FastGPT 独立部署包 + 物理考研交互式诊断工作流。

本项目是**独立平行实验**，与同一台机器上的 `PhysicsPrep`（Gradio + SQLite）**完全隔离**：
不共享目录、端口、数据库、数据卷、Compose 项目，也不引用其任何文件。

---

## 0. 当前状态（请先读这一段）

| 部分 | 状态 |
| --- | --- |
| FastGPT 全栈容器 | **未部署**。本机没有安装 Docker，且安装它需要管理员权限并改动系统组件（详见 `FASTGPT_DEPLOY_REPORT.md`） |
| FastGPT 部署配置 | ✅ 已完成，基于官方 v4.17.1 模板定制，已做隔离与安全改造 |
| 物理诊断工作流（本地实现） | ✅ **可立即运行并已通过 45 项端到端验收测试** |
| 题库（10 题） | ✅ 已通过结构校验（12 项）与物理量独立复算（10 项） |
| 学校 GenAI API 接入 | ⚠️ 代码与测试工具已就绪，**等待你在 `env/.env` 填入 API Address / Key / 模型 ID** |
| FastGPT 端工作流 | ⚠️ 已给出经源码核验的节点规格与提示词，需在 Docker 可用后于界面搭建 |

---

## 1. 目录说明

```
fastgpt-physics-lab/
├── docker-compose.yml          # 基于官方 v4.17.1 模板的隔离版 Compose（仅回环、无固定容器名）
├── SOURCES.md                  # 版本、镜像 tag、官方资料核验记录、改造清单
├── README.md                   # 本文件
├── FASTGPT_DEPLOY_REPORT.md    # 部署与验收报告
├── env/
│   ├── .env.example            # 环境变量模板（可入库）
│   └── .env                    # 你的真实配置（已在 .gitignore，绝不提交）
├── bank/
│   ├── questions.json          # 题源（唯一权威文件，含答案与解析）
│   ├── questions.md            # 派生：人读版（题目区与答案区分离）
│   ├── questions.csv           # 派生：表格版（带 BOM，Excel 不乱码）
│   └── bank.const.js           # 派生：供 FastGPT code 节点使用的题库常量
├── fastgpt/
│   ├── WORKFLOW.md             # 工作流规格（节点、字段、提示词、判定规则）
│   └── WORKFLOW.blueprint.json # 工作流蓝图（节点/边/变量，供照着搭）
├── scripts/
│   └── mongo-replica-init.sh   # MongoDB 首次启动时初始化单节点副本集 rs0
│                               # （走官方 initdb.d 机制；放文件里以绕开 Compose 变量插值）
├── tools/
│   ├── diagnosis-server.mjs    # 本地诊断服务（工作流实现，零第三方依赖）
│   ├── index.html              # 交互界面（可点击选项 + KaTeX 公式）
│   ├── genai.mjs               # 学校 GenAI（OpenAI 兼容）客户端，含端点自动探测
│   ├── diagnosis-server 的配套测试与工具见下
│   ├── genai-conntest.mjs      # GenAI 连通性测试（7 项）
│   ├── e2e-test.mjs            # 端到端验收测试（45 项）
│   ├── validate-bank.mjs       # 题库结构校验（12 项）
│   ├── physics-checks.mjs      # 题库物理量独立复算（10 项）
│   ├── export-bank.mjs         # 题库导出（md / csv / const）
│   ├── check-env.mjs           # 部署前环境预检（只读）
│   ├── new-secrets.mjs         # 随机密钥生成
│   └── mock-openai.mjs         # 本地模拟 OpenAI 服务（仅自测接入管道）
├── third_party/katex/          # 本地 KaTeX（公式离线渲染，不依赖 CDN）
└── data/                       # 运行期数据（已 gitignore）
```

---

## 2. 快速开始

### 2.1 立即可用：本地诊断工作流

```bash
cd fastgpt-physics-lab

# （可选）生成随机内部密钥，填充 env/.env 中的占位符
node tools/new-secrets.mjs --write

# 启动（仅监听 127.0.0.1:3101）
node tools/diagnosis-server.mjs
```

浏览器打开 **http://127.0.0.1:3101** → 选「力学」→ 选章节 → 开始诊断。

未配置 GenAI 时：判分、解析、反馈、报告统计**全部可用**；只有「模型错因分析」和
「模型学习建议」两项会显示明确的不可用原因（不会伪造内容）。

### 2.2 填写学校 GenAI 参数

```bash
cp env/.env.example env/.env     # 若还没有
# 编辑 env/.env，只需填三个：
#   GENAI_BASE_URL=https://<学校网关>/v1
#   GENAI_API_KEY=<学校提供的 Key>
#   GENAI_MODEL=<学校提供的模型 ID>
```

然后验证连通性：

```bash
node tools/genai-conntest.mjs
```

该脚本会逐项验证：端点探测 → 认证 → Chat Completions → 中文回答 → JSON 指令遵循 →
无效模型处理 → 模型列表（可选）→ Embedding 是否存在（可选）。
全程 `max_tokens` 很小，不消耗大量配额，且**不会打印密钥**。

### 2.3 无密钥也能自测接入管道

```bash
node tools/mock-openai.mjs        # 终端 A：本地模拟网关（127.0.0.1:3199）
# 终端 B：
GENAI_BASE_URL=http://127.0.0.1:3199 \
GENAI_API_KEY=mock-key-for-pipeline-test \
GENAI_MODEL=mock-model-a \
node tools/genai-conntest.mjs
```

### 2.4 部署 FastGPT 全栈（需先装好 Docker）

```bash
node tools/check-env.mjs          # 只读预检，不会修改任何东西

# 预检通过后：
docker compose --env-file env/.env up -d

# 查看状态 / 日志
docker compose ps
docker compose logs -f fastgpt-app

# 停止本项目（只影响本项目）
docker compose --env-file env/.env down
```

> 项目名 `fastgpt-physics-lab` 已写在 `docker-compose.yml` 的顶层 `name:` 字段里，
> 因此**不加 `-p` 参数也不会与机器上其它 Compose 项目冲突**。
> 想更保险也可以显式带上：`docker compose -p fastgpt-physics-lab ...`
>
> **严禁**执行 `docker system prune`、`docker volume prune`、不带项目限定的批量停止
> 等全局命令——那会影响机器上其它项目。

---

## 3. 安全与隔离设计

### 端口（全部只绑定 127.0.0.1）

| 端口 | 用途 | 归属 |
| --- | --- | --- |
| 3100 | FastGPT Web 控制台 | 本项目（容器内 3000） |
| 3101 | 本地诊断工作流 | 本项目（可立即运行） |
| 3102 | Agent Sandbox Proxy | 本项目（容器内 1006，预留） |

- **3100 已实测可用**：连续 15 次 `bind` 全部成功，并完成一次真实 HTTP 请求。
  （早期曾测得 `EACCES` 并据此判断"平台策略禁止绑定"，后经复测确认**该结论是错的**，已改回 3100。）
- MongoDB / Redis / pgvector / MinIO 全部只存在于 Compose 私有网络，**不映射到宿主机**。
- 已从上游模板中移除两个会挂载 `/var/run/docker.sock` 的服务
  （`opensandbox-server`、`volume-manager`），以及非必需的 AI Proxy 层。

### 与 PhysicsPrep 的隔离

- 独立目录、独立 Compose 项目名（`fastgpt-physics-lab`）、独立数据卷、独立网络；
- 删除全部 `container_name`，由 Compose 生成 `fastgpt-physics-lab-*` 前缀名，杜绝重名；
- 不引用、不读取、不写入 PhysicsPrep 的任何文件或数据库；
- 会话数据只写 `data/diagnosis-sessions.json`。

### 密钥处理

- 密钥只从 `env/.env` 或进程环境变量读取，**不写进代码、不进 Git、不打印**；
- `env/.env` 已在 `.gitignore` 中；`env/.env.example` 全部留空或占位；
- 所有错误信息经 `redact()` 脱敏后才输出；
- 接口响应已实测不含任何密钥字面量。

---

## 4. 常用命令

```bash
# 测试套件
node tools/validate-bank.mjs     # 题库结构与一致性（12 项）
node tools/physics-checks.mjs    # 物理量独立复算（10 项）
node tools/compose-check.mjs     # Compose 校验，含真实解析器验证与端口断言（40 项，无需 Docker）
node tools/workflow-check.mjs    # 工作流蓝图校验，对照 v4.17.1 源码枚举（94 项）
node tools/e2e-test.mjs          # 端到端验收（45 项，需诊断服务已在运行）

# 题库维护（改完 questions.json 后重新生成派生文件）
node tools/export-bank.mjs

# 密钥
node tools/new-secrets.mjs           # 只打印
node tools/new-secrets.mjs --write   # 直接写入 env/.env
```

> 完整测试合计 **213 项**（另含 GenAI 接入管道 12 项，见 `FASTGPT_DEPLOY_REPORT.md` 第四节）。
>
> 两个校验器都不依赖 Docker：
> - `compose-check.mjs` 会调用真实的 `docker compose config`（**只需二进制、不需要 daemon**）
>   做权威解析；找不到二进制时会跳过该段并打印下载命令。
> - `workflow-check.mjs` 直接从本地 FastGPT 源码抽取 `FlowNodeTypeEnum` 等权威枚举来校验蓝图，
>   并强制「提交前不得泄露答案」与「跨节点引用必须存在」。源码缓存不可用时降级为内置枚举
>   并**明确标注权威性下降**。

---

## 5. 已知限制

1. **FastGPT 未实际部署**：本机无 Docker，安装需管理员权限并改动系统组件。
   本项目已把部署工作做到"Docker 一就绪即可 `up -d`"的程度，但**不能声称 FastGPT 已接通**。
2. **学校 GenAI 未实测**：`GENAI_*` 参数尚未填写，因此真实模型响应、
   限流、Embedding 可用性均**未经真实验证**（接入管道已用本地模拟服务验证）。
3. **题库未经人工复核**：10 道题为本次原创编写，已通过结构校验与物理量独立复算，
   但仍建议由教师人工复核后再用于正式教学。
4. **FastGPT 端工作流需手动搭建**：未提供可直接导入的导出文件——
   FastGPT 的导入 JSON 含界面布局坐标等版本相关字段，手写无法保证与当前版本兼容。
   为避免交付"看着能导入、实际报错"的文件，改为提供经源码核验的节点规格（`fastgpt/WORKFLOW.md`）。
5. **无跨会话掌握度数据库**：第一版只用工作流变量与会话记录，不假装聊天历史等于学生能力库。

---

## 6. 相关文档

- `FASTGPT_DEPLOY_REPORT.md` — 实际执行命令、验收结果、资源隔离对比
- `SOURCES.md` — 版本来源、镜像 tag、官方资料核验方式
- `fastgpt/WORKFLOW.md` — 工作流节点规格、提示词、判定规则
