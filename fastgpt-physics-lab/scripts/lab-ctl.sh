#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# lab-ctl.sh — fastgpt-physics-lab 的启动 / 停止 / 状态 / 备份
#
# ⚠ 安全约定（本脚本严格遵守，请勿改成全局清理）：
#   - 只操作 Compose 项目名 `fastgpt-physics-lab`（已在 docker-compose.yml
#     顶层用 name: 固定），绝不影响机器上其它容器/项目。
#   - 不做 docker system prune / docker volume prune。
#   - 不 docker stop 其它容器，不删其它项目的卷或网络。
#
# 用法：
#   ./scripts/lab-ctl.sh up        启动全部服务
#   ./scripts/lab-ctl.sh down      停止并移除本项目容器（**保留数据卷**）
#   ./scripts/lab-ctl.sh status    查看状态
#   ./scripts/lab-ctl.sh logs      跟踪日志
#   ./scripts/lab-ctl.sh backup    备份 MongoDB + MinIO 到 backups/
#   ./scripts/lab-ctl.sh health    逐服务健康检查
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROJECT=fastgpt-physics-lab
ENV_FILE=env/.env
COMPOSE=(docker compose --project-name "$PROJECT" --env-file "$ENV_FILE")

# Windows 上 Docker CLI 可能不在当前 PATH 里；若找不到就补上默认安装位置
if ! command -v docker >/dev/null 2>&1; then
  for p in "/c/Program Files/Docker/Docker/resources/bin" "/mnt/c/Program Files/Docker/Docker/resources/bin"; do
    if [ -x "$p/docker" ] || [ -x "$p/docker.exe" ]; then PATH="$p:$PATH"; break; fi
  done
fi
export PATH

die() { echo "错误：$*" >&2; exit 1; }

require_env() {
  [ -f "$ENV_FILE" ] || die "缺少 $ENV_FILE。请先执行：cp env/.env.example env/.env 并填入密钥。"
}

case "${1:-}" in
  up)
    require_env
    echo "启动 $PROJECT ..."
    "${COMPOSE[@]}" up -d
    echo
    "${COMPOSE[@]}" ps
    ;;

  down)
    require_env
    echo "停止 $PROJECT（数据卷保留，不删除任何数据）..."
    # 注意：不加 -v，避免删除数据卷
    "${COMPOSE[@]}" down
    echo "已停止。数据卷仍保留，下次 up 会复用。"
    ;;

  status)
    require_env
    "${COMPOSE[@]}" ps
    ;;

  logs)
    require_env
    "${COMPOSE[@]}" logs -f --tail 100
    ;;

  health)
    require_env
    printf '%-52s %s\n' "服务" "状态"
    for c in $("${COMPOSE[@]}" ps --format '{{.Name}}'); do
      s=$(docker inspect "$c" --format '{{.State.Status}}{{if .State.Health}} / {{.State.Health.Status}}{{end}}' 2>/dev/null || echo "未知")
      printf '%-52s %s\n' "$c" "$s"
    done
    ;;

  backup)
    require_env
    TS=$(date +%Y%m%d-%H%M%S)
    OUT="$ROOT/backups/$TS"
    mkdir -p "$OUT"

    # 从 .env 读取凭据（不打印到终端）
    getv() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2-; }
    MU=$(getv MONGO_ROOT_USERNAME); MP=$(getv MONGO_ROOT_PASSWORD)
    MINU=$(getv MINIO_ROOT_USER); MINP=$(getv MINIO_ROOT_PASSWORD)

    echo "备份 MongoDB -> $OUT/fastgpt-mongo.archive"
    docker exec "fastgpt-physics-lab-fastgpt-mongo-1" \
      mongodump -u "$MU" -p "$MP" --authenticationDatabase admin \
      --db fastgpt --archive --gzip > "$OUT/fastgpt-mongo.archive"

    echo "备份 MinIO 数据卷（本项目专属卷）-> $OUT/minio-data.tar.gz"
    # 用一个临时容器读取本项目的卷，不触碰其它卷
    docker run --rm \
      -v "${PROJECT}_fastgpt-minio:/data:ro" \
      -v "$OUT:/backup" \
      alpine:3 tar czf /backup/minio-data.tar.gz -C /data . 2>/dev/null \
      || echo "  (跳过 MinIO：本地无 alpine 镜像且拉取失败，可稍后重试)"

    echo "备份 .env 配置（含密钥，请妥善保管）-> $OUT/.env"
    cp "$ENV_FILE" "$OUT/.env"
    chmod 600 "$OUT/.env" 2>/dev/null || true

    echo
    echo "备份完成：$OUT"
    ls -lh "$OUT"
    echo
    echo "⚠ 该目录包含数据库与密钥，不要上传到任何公开位置。"
    ;;

  *)
    sed -n '2,20p' "$0"
    exit 1
    ;;
esac
