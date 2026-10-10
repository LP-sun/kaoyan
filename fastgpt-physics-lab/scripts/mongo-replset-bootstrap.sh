#!/bin/bash
# ---------------------------------------------------------------------------
# mongo-replset-bootstrap.sh
#
# 作用：确保单节点副本集 rs0 已初始化，并确保当前容器是 PRIMARY。
#       由 mongo-entrypoint.sh 在每次容器启动时调用（幂等）。
#
# 为什么不能只依赖 MongoDB 官方镜像的 /docker-entrypoint-initdb.d/ 机制：
#   该机制**仅在数据目录为空（首次初始化）时**执行。
#   部署中真实踩到的坑：mongod 因缺少 keyFile 反复启动失败时，
#   数据目录已被写入（账号已建），于是 initdb.d 再也不会执行，
#   导致副本集始终未初始化。表现是应用侧报
#     MongooseError: Connection operation buffering timed out after 10000ms
#   也就是连接一直"缓冲"、从不真正建立——因为单节点副本集未 initiate 时
#   驱动无法完成副本集发现。
#   所以副本集初始化必须放在启动路径上幂等执行，而不是只放在 initdb.d。
#
# 为什么要用本地 127.0.0.1 中继：
#   副本集未初始化时，mongod 只接受本地连接（未鉴权的 localhost 例外），
#   因此先启动一个绑定 127.0.0.1 的临时 mongod 来完成 rs.initiate()。
#   initiate 完成后它在后台把配置传播给复制集，再关闭它并正式启动
#   带 keyFile + --replSet 的 mongod。
#
# 幂等性：第二次启动时 rs.status() 已可用，直接跳过，不做任何改动。
# ---------------------------------------------------------------------------
set -uo pipefail

LOG_PREFIX="[replset-bootstrap]"
DBPATH="${MONGO_DBPATH:-/data/db}"
PORT=27017

log() { echo "$LOG_PREFIX $*"; }

# ---------------------------------------------------------------------------
# 0. 首次运行（数据目录里没有任何 WiredTiger 文件）时，什么都不做：
#    交给官方 entrypoint 走标准的 initdb 流程（建管理员账号 + 执行 initdb.d），
#    那条路径本身会正确处理副本集，且此时本地启动会与官方流程冲突。
# ---------------------------------------------------------------------------
if ! ls "$DBPATH"/WiredTiger* >/dev/null 2>&1; then
  log "数据目录为空，跳过自举（交给官方 entrypoint 的 initdb 流程）"
  exit 0
fi

# ---------------------------------------------------------------------------
# 1. 直接连接试试（mongod 可能已经在跑且副本集已就绪）
# ---------------------------------------------------------------------------
js_status='const s=(()=>{try{return rs.status()}catch(e){return null}})(); if(s&&s.ok===1&&s.members&&s.members.length){print("READY "+s.set+" "+s.members[0].stateStr)}else{print("NOT_READY")}'

read_status() {
  local out
  out="$(mongo --quiet --host 127.0.0.1:$PORT --eval "$js_status" 2>/dev/null || true)"
  echo "$out"
}

if command -v mongo >/dev/null 2>&1; then
  st="$(read_status)"
  if echo "$st" | grep -q "READY"; then
    log "副本集已就绪：$st"
    exit 0
  fi
else
  log "镜像内没有 mongo shell，无法自举副本集；跳过"
  exit 0
fi

# ---------------------------------------------------------------------------
# 2. 未就绪：本地无鉴权拉起临时 mongod，完成 rs.initiate()
# ---------------------------------------------------------------------------
log "副本集未就绪，启动临时本地 mongod 以完成初始化..."

# 清掉上次异常退出可能残留的锁文件，否则 mongod 拒绝启动
rm -f "$DBPATH/mongod.lock" 2>/dev/null || true

TMPLOG=/tmp/replset-bootstrap-mongod.log
mongod --dbpath "$DBPATH" --port $PORT --bind_ip 127.0.0.1 \
       --replSet rs0 --fork --logpath "$TMPLOG" >/dev/null 2>&1
started=$?

if [ $started -ne 0 ]; then
  log "临时 mongod 启动失败，输出如下（末尾 20 行）："
  tail -n 20 "$TMPLOG" 2>/dev/null | sed "s/^/$LOG_PREFIX   /"
  # 可能是"数据目录已被另一个 mongod 占用"——那说明正式 mongod 正在跑，
  # 此时不该继续，直接退出让正式 mongod 自己决定。
  exit 0
fi

# 等待可连接
for i in $(seq 1 30); do
  if mongo --quiet --host 127.0.0.1:$PORT --eval 'db.runCommand({ping:1}).ok' >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# 初始化副本集
INIT_JS='const target="fastgpt-mongo:27017";
let ok=false;
try { const s=rs.status(); ok = (s&&s.ok===1&&s.members&&s.members.length>0); } catch(e) { ok=false; }
if (ok) { print("ALREADY "+rs.status().set); }
else { const r=rs.initiate({_id:"rs0",members:[{_id:0,host:target}]}); print("INITIATED "+JSON.stringify(r)); }'

RESULT="$(mongo --quiet --host 127.0.0.1:$PORT --eval "$INIT_JS" 2>&1 || true)"
log "rs.initiate 结果: $RESULT"

# 等它真正选主；单节点通常几秒内完成
for i in $(seq 1 20); do
  sleep 1
  if mongo --quiet --host 127.0.0.1:$PORT --eval 'const s=rs.status(); print(s.members[0].stateStr)' 2>/dev/null | grep -q PRIMARY; then
    log "副本集已成为 PRIMARY"
    break
  fi
done

# 关闭临时 mongod，让出端口给正式 mongod
mongo --quiet --host 127.0.0.1:$PORT --eval 'db.getSiblingDB("admin").shutdownServer()' >/dev/null 2>&1 || true
for i in $(seq 1 20); do
  if ! mongo --quiet --host 127.0.0.1:$PORT --eval 'db.runCommand({ping:1}).ok' >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
rm -f "$DBPATH/mongod.lock" 2>/dev/null || true
log "临时 mongod 已关闭，移交正式启动"
exit 0
