#!/bin/bash
# ---------------------------------------------------------------------------
# mongo-entrypoint.sh
#
# 作用：在 mongod 启动**之前**准备好副本集内部认证所需的 keyFile，
#       然后把控制权交还给 MongoDB 官方入口脚本。
#
# 为什么必须有 keyFile：
#   本项目的 mongod 同时开启了「鉴权」（MONGO_INITDB_ROOT_* 会建管理员账号）
#   和「副本集」（--replSet rs0，FastGPT 的事务依赖它）。
#   MongoDB 的硬性要求是：
#     BadValue: security.keyFile is required when authorization is enabled
#               with replica sets
#   也就是「鉴权 + 副本集」组合下**必须**提供 keyFile，否则 mongod 直接退出。
#   （这是部署中实测到的失败原因：容器反复重启，退出码 2。）
#
# 为什么需要这个包装脚本（不能直接把 keyFile 挂载进去）：
#   1. keyFile 必须在 mongod 进程启动前就存在于文件系统；
#   2. MongoDB 对 keyFile 权限有强制要求——若同组/他人可读，mongod 会拒绝启动。
#      Docker 绑定挂载进来的文件属主是宿主机的 uid（通常是 root），
#      而镜像内 mongod 以 mongodb 用户运行，直接挂载会导致「不可读」或「权限过宽」，
#      两种情况都会让 mongod 启动失败。
#   因此这里在容器内以 root 身份先把 keyFile 落到数据卷里、设成 400 且属主为 mongodb。
#
# 为什么 keyFile 内容用固定字符串而不是随机生成：
#   单节点副本集没有节点间通信，keyFile 只是一个"存在且合法"的凭据。
#   用固定值可保证**容器重建后仍能连上已有数据**（随机生成会在每次重建时
#   让新 mongod 与旧数据里的认证信息不一致）。它不作为对外密钥使用，
#   外部访问一律用 MONGO_ROOT_USERNAME/PASSWORD。
#
# 说明：本脚本位于挂载文件中，不经过 Compose 的变量插值（见同目录
#       mongo-replica-init.sh 的说明），因此内部可安全使用 $VAR。
# ---------------------------------------------------------------------------
set -euo pipefail

KEYFILE=/data/db/mongo-keyfile

# MongoDB 对 keyFile 内容有**字符集限制**：只允许 base64 字符（A-Za-z0-9+/），
# 长度 6~1024 字节。踩过的坑：最初用带连字符的可读字符串，mongod 报
#   UnsupportedFormat: invalid char in key file ... 
# 因此这里用 openssl 生成标准 base64（若容器内没有 openssl 则退回 tr 方案）。
#
# 只在文件不存在时生成；生成后持久化在数据卷里，容器重建时复用同一个值，
# 保证新 mongod 与已有数据中的认证信息一致。
if [ ! -f "$KEYFILE" ]; then
  if command -v openssl >/dev/null 2>&1; then
    # 512 字节随机数据 -> 约 684 个 base64 字符，全部落在合法字符集内
    openssl rand -base64 512 | tr -d '\n' > "$KEYFILE"
  else
    # 退路：/dev/urandom 取随机字节再 base64 编码
    head -c 512 /dev/urandom | base64 | tr -d '\n' > "$KEYFILE"
  fi
  printf '\n' >> "$KEYFILE"
  echo "[mongo-entrypoint] 已生成 keyFile（base64）: $KEYFILE"
else
  echo "[mongo-entrypoint] keyFile 已存在，复用: $KEYFILE"
fi

# 自检：确认内容只含 base64 字符，避免再次出现 invalid char 导致重启循环
if LC_ALL=C grep -q '[^A-Za-z0-9+/]' "$KEYFILE"; then
  echo "[mongo-entrypoint] 检测到非法字符，重新生成 keyFile"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 512 | tr -d '\n' > "$KEYFILE"
  else
    head -c 512 /dev/urandom | base64 | tr -d '\n' > "$KEYFILE"
  fi
  printf '\n' >> "$KEYFILE"
fi
echo "[mongo-entrypoint] keyFile 长度: $(wc -c < "$KEYFILE") 字节"

# MongoDB 要求 keyFile 权限不得宽于 600（同组/他人不可读）。
chmod 400 "$KEYFILE" || chmod 600 "$KEYFILE"

# mongod 以 mongodb 用户运行，必须让该用户可读。
if id mongodb >/dev/null 2>&1; then
  chown mongodb:mongodb "$KEYFILE" 2>/dev/null || true
  echo "[mongo-entrypoint] keyFile 属主已设为 mongodb，权限 400"
else
  echo "[mongo-entrypoint] 警告：镜像内无 mongodb 用户，保持 root 属主"
fi

# 同时修正数据目录属主（绑定卷首次使用时可能是 root）
if id mongodb >/dev/null 2>&1; then
  chown -R mongodb:mongodb /data/db 2>/dev/null || true
fi

# 交还给官方入口脚本。
# 它会在初始化阶段临时移除 --keyFile 与 --replSet（这是官方针对 initdb 的设计），
# 初始化完成后用我们传入的完整参数正式启动 mongod，
# 并且会去执行 /docker-entrypoint-initdb.d/ 下的副本集初始化脚本。
#
# 额外一步：在移交前先幂等地确保副本集已初始化。
# 原因是官方 initdb.d 机制**只在数据目录为空时**执行一次，
# 而 mongod 早期启动失败会让数据目录被写入，之后 initdb.d 永远不再运行，
# 副本集就一直是未初始化状态（应用侧表现为连接缓冲超时）。
echo "[mongo-entrypoint] 检查并确保副本集已初始化..."
if [ -x /docker-entrypoint-wrapper/mongo-replset-bootstrap.sh ]; then
  bash /docker-entrypoint-wrapper/mongo-replset-bootstrap.sh || \
    echo "[mongo-entrypoint] 警告：副本集自举脚本返回非零，继续交给官方入口脚本"
else
  echo "[mongo-entrypoint] 未找到自举脚本，跳过"
fi

echo "[mongo-entrypoint] 移交官方入口脚本: $*"
exec /usr/local/bin/docker-entrypoint.sh "$@"
