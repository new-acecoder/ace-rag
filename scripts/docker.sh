#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
ENV_FILE="$ROOT_DIR/.env.docker"
ENV_EXAMPLE="$ROOT_DIR/.env.docker.example"

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

info()  { printf '\033[1;34m[ace-rag]\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m[ok]\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
error() { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; }

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    error "缺少命令: $1"
    exit 1
  }
}

prepare() {
  require_command docker

  if ! docker compose version >/dev/null 2>&1; then
    error "未检测到 Docker Compose V2，请先安装/启用 docker compose。"
    exit 1
  fi

  if ! docker info >/dev/null 2>&1; then
    error "Docker daemon 未运行，请先启动 Docker Desktop / OrbStack / Docker Engine。"
    exit 1
  fi

  if [[ ! -f "$ENV_FILE" ]]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    warn "已根据 .env.docker.example 生成 .env.docker。当前凭据仅适合本地开发。"
  fi
}

wait_healthy() {
  local services=(postgres redis etcd minio rabbitmq milvus)
  # Milvus allows a 90s start period followed by up to 20 checks every 15s.
  local deadline=$((SECONDS + 420))

  info "等待核心中间件健康检查通过..."
  while (( SECONDS < deadline )); do
    local all_healthy=true
    for service in "${services[@]}"; do
      local cid status
      cid="$(compose ps -q "$service" 2>/dev/null || true)"
      if [[ -z "$cid" ]]; then
        all_healthy=false
        break
      fi
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || true)"
      if [[ "$status" != "healthy" ]]; then
        all_healthy=false
        break
      fi
    done

    if [[ "$all_healthy" == true ]]; then
      ok "PostgreSQL / Redis / etcd / MinIO / RabbitMQ / Milvus 全部健康。"
      return 0
    fi
    sleep 3
  done

  error "等待服务健康超时。当前状态："
  compose ps
  echo
  warn "可执行 ./scripts/docker.sh logs 查看日志。"
  return 1
}

url_encode() {
  local value="$1"
  local encoded=""
  local char hex
  local i
  local LC_ALL=C

  for ((i = 0; i < ${#value}; i++)); do
    char="${value:i:1}"
    case "$char" in
      [a-zA-Z0-9.~_-]) encoded+="$char" ;;
      *)
        printf -v hex '%%%02X' "'$char"
        encoded+="$hex"
        ;;
    esac
  done

  printf '%s' "$encoded"
}

print_endpoints() {
  local postgres_user=ace_rag postgres_password=ace_rag_dev postgres_db=ace_rag postgres_db_uri
  local postgres_port=5432 redis_port=6379 milvus_port=19530 attu_port=3000 minio_api_port=9000 minio_console_port=9001 rabbitmq_port=5672 rabbitmq_management_port=15672
  local key value

  while IFS='=' read -r key value; do
    case "$key" in
      POSTGRES_USER) postgres_user="$value" ;;
      POSTGRES_PASSWORD) postgres_password="$value" ;;
      POSTGRES_DB) postgres_db="$value" ;;
      POSTGRES_PORT) postgres_port="$value" ;;
      REDIS_PORT) redis_port="$value" ;;
      MILVUS_PORT) milvus_port="$value" ;;
      ATTU_PORT) attu_port="$value" ;;
      MINIO_API_PORT) minio_api_port="$value" ;;
      MINIO_CONSOLE_PORT) minio_console_port="$value" ;;
      RABBITMQ_PORT) rabbitmq_port="$value" ;;
      RABBITMQ_MANAGEMENT_PORT) rabbitmq_management_port="$value" ;;
    esac
  done < <(compose config --environment)

  postgres_user="$(url_encode "$postgres_user")"
  postgres_password="$(url_encode "$postgres_password")"
  postgres_db_uri="$(url_encode "$postgres_db")"

  cat <<EOF

本地连接地址：
  PostgreSQL : 127.0.0.1:${postgres_port} / db=${postgres_db}
  Redis      : redis://127.0.0.1:${redis_port}/0
  Milvus     : http://127.0.0.1:${milvus_port}
  Attu UI    : http://127.0.0.1:${attu_port}
  MinIO API  : 127.0.0.1:${minio_api_port}
  MinIO UI   : http://127.0.0.1:${minio_console_port}
  RabbitMQ   : amqp://127.0.0.1:${rabbitmq_port}
  RabbitMQ UI: http://127.0.0.1:${rabbitmq_management_port}

FastAPI 建议环境变量：
  POSTGRES_URI=postgresql://${postgres_user}:${postgres_password}@127.0.0.1:${postgres_port}/${postgres_db_uri}
  REDIS_URL=redis://127.0.0.1:${redis_port}/0
  MILVUS_URI=http://127.0.0.1:${milvus_port}
  MINIO_ENDPOINT=127.0.0.1:${minio_api_port}
  RABBITMQ_URL=amqp://ace_rag:ace_rag_dev@127.0.0.1:${rabbitmq_port}/
EOF
}

up() {
  prepare
  info "拉取 Ace RAG 中间件镜像..."
  compose pull
  info "启动 Ace RAG 中间件..."
  compose up -d --remove-orphans
  wait_healthy
  compose ps
  print_endpoints
}

down() {
  prepare
  info "停止 Ace RAG 中间件（保留持久化数据）..."
  compose down --remove-orphans
  ok "已停止。"
}

restart() {
  prepare
  info "重启 Ace RAG 中间件..."
  compose down --remove-orphans
  compose up -d --remove-orphans
  wait_healthy
  compose ps
}

status() {
  prepare
  compose ps
}

logs() {
  prepare
  compose logs -f --tail=200 "${@:2}"
}

clean() {
  prepare
  warn "该操作会删除 PostgreSQL、Redis、Milvus、etcd、MinIO、RabbitMQ 的全部本地数据。"
  read -r -p "确认彻底清理？输入 YES 继续: " answer
  if [[ "$answer" != "YES" ]]; then
    info "已取消。"
    exit 0
  fi
  compose down -v --remove-orphans
  ok "容器、网络和数据卷已删除。"
}

usage() {
  cat <<'EOF'
Ace RAG middleware helper

Usage:
  ./scripts/docker.sh [command]

Commands:
  up       一键拉取并启动全部中间件（默认）
  down     停止容器，保留数据
  restart  重启全部中间件
  status   查看容器状态
  logs     查看全部日志；可追加服务名，例如 logs milvus
  clean    删除容器和全部持久化数据（危险）
  help     查看帮助
EOF
}

cmd="${1:-up}"
case "$cmd" in
  up) up ;;
  down) down ;;
  restart) restart ;;
  status) status ;;
  logs) logs "$@" ;;
  clean) clean ;;
  help|-h|--help) usage ;;
  *)
    error "未知命令: $cmd"
    usage
    exit 1
    ;;
esac
