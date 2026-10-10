#!/bin/bash
# ---------------------------------------------------------------------------
# mongo-replica-init.sh
#
# 作用：在 MongoDB 首次启动时把单节点副本集 rs0 初始化好。
#       FastGPT 使用事务，MongoDB 必须处于副本集模式。
#
# 为什么放在独立文件里而不是写在 docker-compose.yml 的 entrypoint 里：
#   Docker Compose 的变量插值发生在 YAML 解析**之前**，因此连 YAML 单引号
#   字符串也挡不住 $VAR 被替换（已实测：会被替换成明文密码）。
#   写在挂载文件里则完全不经过 Compose 的插值，彻底避开转义歧义。
#
# 本脚本由 MongoDB 官方镜像的 docker-entrypoint.sh 通过
#   /docker-entrypoint-initdb.d/
# 机制调用（仅在数据目录为空、即首次初始化时执行）。因此此处
# **不需要**自己启动 mongod，也不需要等待端口就绪。
#
# 前提：容器内已注入 MONGO_ROOT_USERNAME / MONGO_ROOT_PASSWORD 环境变量，
#       且与 MONGODB_URI 中使用的账号一致。
# ---------------------------------------------------------------------------
set -euo pipefail

echo "[replica-init] 开始初始化副本集 rs0 ..."

# 官方镜像在运行本目录脚本前，已经用 MONGO_INITDB_ROOT_USERNAME/PASSWORD
# 建好了管理员账号。这里用同一组凭据连过去。
AUTH_ARGS=()
if [ -n "${MONGO_ROOT_USERNAME:-}" ]; then
  AUTH_ARGS+=(-u "$MONGO_ROOT_USERNAME")
  AUTH_ARGS+=(-p "$MONGO_ROOT_PASSWORD")
  AUTH_ARGS+=(--authenticationDatabase admin)
fi

mongo "${AUTH_ARGS[@]}" --quiet --eval '
  const target = "fastgpt-mongo:27017";
  let inited = false;
  try { inited = rs.status().ok === 1; } catch (e) { inited = false; }
  if (inited) {
    print("[replica-init] 副本集已存在，跳过");
  } else {
    const r = rs.initiate({ _id: "rs0", members: [{ _id: 0, host: target }] });
    print("[replica-init] rs.initiate -> " + JSON.stringify(r));
  }
'

echo "[replica-init] 完成"
