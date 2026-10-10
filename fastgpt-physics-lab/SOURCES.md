# 来源与版本记录（SOURCES）

本文件记录本项目采用的 FastGPT 版本、配置来源与核验方式。
**不含任何密钥。**

---

## 1. 采用的版本

| 项目 | 值 |
| --- | --- |
| FastGPT 稳定版本（tag） | **v4.17.1**（2026-09-30 发布，最新稳定 tag） |
| 部署镜像版本 | **fastgpt:v4.17.0**（官方 `deploy/version/main/args.json` 中指定的 tag） |
| 上一次稳定版本 | v4.17.0（2026-09-11） |
| 镜像源 | `registry.cn-hangzhou.aliyuncs.com/fastgpt/*`（国内源，官方 `args.json` 的 `images.cn`） |

> 说明：v4.17.1 是仓库 tag，但官方 `main` 版部署参数的镜像 tag 是 `v4.17.0`。
> 本项目严格按官方 `args.json` 固定镜像版本，**不使用 `latest`**。

## 2. 组件与镜像版本（全部取自官方 `deploy/version/main/args.json`）

| 组件 | 镜像 | Tag |
| --- | --- | --- |
| FastGPT 主服务 | `registry.cn-hangzhou.aliyuncs.com/fastgpt/fastgpt` | v4.17.0 |
| 系统插件 | `.../fastgpt/fastgpt-plugin` | v1.1.3 |
| 代码沙箱 | `.../fastgpt/fastgpt-code-sandbox` | v4.17.0 |
| Agent Sandbox Proxy | `.../fastgpt/fastgpt-agent-sandbox-proxy` | v0.3.0 |
| MongoDB | `.../fastgpt/mongo` | 5.0.32 |
| Redis | `.../fastgpt/redis` | 7.2-alpine |
| MinIO | `.../fastgpt/minio` | RELEASE.2025-09-07T16-13-09Z |
| 向量库（pgvector） | `.../fastgpt/pgvector` | 0.8.0-pg15 |

**被本项目主动移除的上游组件**（安全审查结论见 `docker-compose.yml` 顶部注释）：

| 组件 | 上游镜像 | 移除原因 |
| --- | --- | --- |
| `fastgpt-opensandbox-server` | `opensandbox/server:v0.2.2` | 挂载 `/var/run/docker.sock`（读写），可控制宿主机 Docker |
| `fastgpt-volume-manager` | `fastgpt-agent-volume-manager:v0.3.0` | 挂载 `/var/run/docker.sock`（只读） |
| `fastgpt-aiproxy` + `fastgpt-aiproxy-pg` | `labring/aiproxy:v0.6.5`、`pgvector:0.8.0-pg15` | 本项目直接使用学校 OpenAI 兼容接口，不需要额外 AI 代理层；去掉可少两个常驻容器，降低内存占用 |

以上三个均非诊断工作流的必需组件。

## 3. 官方资料核验记录

| 资料 | 地址 | 获取方式 | 结果 |
| --- | --- | --- | --- |
| 官方部署 SKILL 说明 | `https://doc.fastgpt.cn/deploy/SKILL.md` | Node fetch（本机代理） | 200，已通读；确认默认端口 3000 / 3006 / 3003、默认向量库为 PostgreSQL+pgvector、核心服务清单 |
| 官方 Docker 部署文档页 | `https://doc.fastgpt.cn/zh-CN/self-host/deploy/docker` | Node fetch | 200 |
| GitHub 仓库（版本） | `https://github.com/labring/FastGPT` | tags.atom / releases.atom | v4.17.1 为最新稳定 tag |
| 官方 Compose 模板 | `deploy/version/main/docker-compose.template.yml` @ tag v4.17.1 | 官方 tarball 解包 | 已作为本项目 compose 的基线 |
| 官方向量库片段 | `deploy/templates/vector/pg.txt` @ v4.17.1 | 同上 | pgvector 服务定义与 `PG_URL` 变量名 |
| 官方镜像版本表 | `deploy/version/main/args.json` @ v4.17.1 | 同上 | 上表全部 tag 来源 |
| 官方应用环境变量模板 | `projects/app/.env.template` @ v4.17.1 | 同上 | 确认 v4.17 模型配置方式与安全开关 |
| 交互节点定义 | `packages/global/core/workflow/template/system/interactive/userSelect.ts`、`formInput.ts` @ v4.17.1 | `git show` | 确认 `flowNodeType`、输入键 `description`/`userSelectOptions`/`userInputForms`、输出键 `selectResult`/`formInputResult`（object） |
| 节点类型枚举 | `packages/global/core/workflow/node/constant.ts` @ v4.17.1 | `git show` | `FlowNodeTypeEnum` 共 **38** 个类型 |
| 输入/输出键枚举 | `packages/global/core/workflow/constants.ts` @ v4.17.1 | `git show` | `NodeInputKeyEnum` **115** 键、`NodeOutputKeyEnum` **35** 键；由 `tools/workflow-check.mjs` 自动读取用于校验蓝图 |
| 官方 Compose 二进制 | `docker/compose` release v5.6.0 (windows-x86_64) | 直接下载 | 用于 `docker compose config` 权威解析验证（**不需要 daemon**） |

### 未采用的官方脚本

- `https://doc.fastgpt.cn/deploy/install.sh`（1415 行）**未执行**。
  任务要求"不要直接执行未经审查的远程 shell 脚本"，且该脚本要求 Docker 已存在。
  另外，该脚本会：
  - 默认把 MCP 地址设置为"检测到的第一个主 IP"（非回环），与本项目"仅 127.0.0.1"的要求冲突；
  - 只支持通过 `FASTGPT_PORT` / `FASTGPT_SANDBOX_PROXY_PORT` 改端口，**不支持把映射改为回环绑定**。
  因此本项目改为直接基于官方模板定制 Compose 文件，逐项完成隔离改造。

## 4. 本项目的改造清单（相对上游模板）

1. 删除全部 `container_name:` —— 由 Compose 自动生成 `fastgpt-physics-lab-*` 前缀名。
2. 端口映射全部加 `127.0.0.1:` 前缀（上游为 `3000:3000`、`3006:1006`、`9000:9000`、`9001:9001`）。
3. 宿主机端口按要求优先使用 **3100**（FastGPT Web）与 **3102**（Sandbox Proxy），本地诊断服务用 **3101**。
   > 纠错记录：早期测得 3100 的 `bind` 返回 `EACCES`，当时判断为"平台策略禁止绑定"并改用 3101。
   > 后续复测（连续 15 次 `bind`/`close` 全部成功 + 一次真实 HTTP 请求通过）证明 3100 可正常使用，
   > 该结论是错的，现已改回 3100。`tools/compose-check.mjs` 已加入断言把"默认端口必须是 3100"
   > 固定下来，防止再次漂移。
4. MinIO 的 9000/9001 默认**不映射**到宿主机。
5. 移除 `opensandbox-server` 与 `volume-manager` 两个挂载 Docker socket 的服务。
6. 移除 AI Proxy 与其 PostgreSQL。
7. `AGENT_SANDBOX_PROVIDER` 置空，不再拉起沙箱容器。
8. 所有密码/密钥改为从 `env/.env` 注入，不硬编码在 Compose 中；上游模板默认密码为 `mypassword` / `1234` / `minioadmin`。
9. 为关键服务加 `deploy.resources.limits.memory`，控制本项目资源占用（不影响其它项目）。
10. 保留官方 `non-root` 相关设置（`security_opt: no-new-privileges` 仅在上游已有的 code-sandbox 上保留）。
11. **修复上游模板的两处密码注入缺陷**（详见 `FASTGPT_DEPLOY_REPORT.md` 第六节）：
    上游模板用硬编码密码 `myusername`/`mypassword`，所以没有暴露这些问题；
    一旦像本项目这样改为从 `.env` 注入，就会踩中：
    - MongoDB `entrypoint` 中的 `"${MONGO_ROOT_USERNAME}"` 是**容器内 shell 运行时**展开的，
      而 Compose 的插值发生在 YAML 解析之前，导致该变量被提前替换或展开为空。
    - `healthcheck` 用 CMD 数组直接展开密码，密码含空格时会被拆词，容器永远 unhealthy，
      而 `fastgpt-app` 依赖它 `service_healthy`，于是**永远不启动**。
    - 官方 `install.sh` 通过字符串替换改密码，因此它能绕开这些问题；
      本项目不使用该脚本，改为手工修正配置。
12. **MongoDB 启动方式改为官方 `initdb.d` 机制**（不再自建 entrypoint）：
    - 去掉 `--keyFile`。它要求密钥文件先于 mongod 存在，而官方入口脚本在 initdb 阶段
      会临时移除该参数（`_mongod_hack_ensure_no_arg_val --keyFile`），上游模板靠自建
      entrypoint 先生成密钥才绕开。单节点副本集 + 仅回环访问下 `--keyFile` 无实际安全收益，
      故直接移除，减少一类启动失败风险。
    - 副本集初始化脚本移到 `scripts/mongo-replica-init.sh`，通过
      `/docker-entrypoint-initdb.d/` 挂载，只在首次初始化时执行一次。
    - 不覆盖容器 `entrypoint`（否则官方入口脚本不会执行 initdb.d），
      `command` 仅设 `mongod --replSet rs0`。
    - 这样处理还顺带解决了 Compose 变量插值的转义歧义：挂载文件的内容完全不经过
      Compose 插值。实测结论：`$$VAR` 在本机 Compose v5.6.0 下**不会**折叠为 `$VAR`，
      会被原样保留（详见 `FASTGPT_DEPLOY_REPORT.md` 第六节第 7、8 项）。
13. 顶层增加 `name: fastgpt-physics-lab`，使隔离项目名成为文件固有属性——
    即使使用者忘记加 `-p` 参数，容器/网络/卷也一定带 `fastgpt-physics-lab_` 前缀。

## 5. 用真实解析器验证（不需要 Docker daemon）

`docker compose config` 只做配置解析，**不需要 Docker 引擎**，因此可以在没有 Docker 的
机器上验证 Compose 配置的正确性。本项目用它做了权威验证：

```bash
# 取得独立 Compose 二进制（约 32 MB，仅解析用）
node .fastgpt-lab-notes/dl.js \
  "https://github.com/docker/compose/releases/download/v5.6.0/docker-compose-windows-x86_64.exe" \
  .verify/docker-compose.exe

# 权威解析验证（已集成进校验器）
node tools/compose-check.mjs
```

实测结论（Compose **v5.6.0**）：
- 项目名、网络名、卷名全部带 `fastgpt-physics-lab_` 前缀；
- 解析后无任何 `container_name`，端口 `host_ip` 全为 `127.0.0.1`；
- `stderr` 为空，无未定义变量警告；
- `$$VAR` **不会**被折叠为 `$VAR`（与部分文档描述不一致，已按实测结论处理）。

## 5. 复现核验的命令

```bash
# 1) 拿官方 tarball（本机 curl 的 Schannel 被限制，改用 Node fetch）
node .fastgpt-lab-notes/dl.js \
  "https://codeload.github.com/labring/FastGPT/tar.gz/refs/tags/v4.17.1" \
  ".fastgpt-lab-notes/fastgpt-v4.17.1.tar.gz"

# 2) 只解出部署相关文件
tar -xzf .fastgpt-lab-notes/fastgpt-v4.17.1.tar.gz -C .fastgpt-lab-notes \
  "FastGPT-4.17.1/deploy" "FastGPT-4.17.1/document/public/deploy"

# 3) 核对镜像 tag
cat .fastgpt-lab-notes/FastGPT-4.17.1/deploy/version/main/args.json

# 4) 核对节点类型
git -C .fastgpt-lab-notes/FastGPT-src show HEAD:packages/global/core/workflow/node/constant.ts
```

> 本机 `curl` 因沙箱限制无法使用 Schannel 建立 TLS（`SEC_E_NO_CREDENTIALS`），
> 因此所有网络抓取改用 Node 内置 `fetch`（自带 OpenSSL）。
> `git` 需要显式切到 OpenSSL 后端：
> `git -c http.sslBackend=openssl -c http.sslCAInfo="C:\Program Files\Git\mingw64\etc\ssl\certs\ca-bundle.crt"`
