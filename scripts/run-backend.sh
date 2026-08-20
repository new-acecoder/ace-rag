#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
API_PID=""
WORKER_PID=""

info() { printf '\033[1;34m[ace-rag]\033[0m %s\n' "$*"; }
error() { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; }

stop_process() {
  local pid="$1"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
  fi
}

cleanup() {
  trap - EXIT INT TERM
  stop_process "$WORKER_PID"
  stop_process "$API_PID"
  wait "$WORKER_PID" 2>/dev/null || true
  wait "$API_PID" 2>/dev/null || true
}

on_signal() {
  info "正在停止 API 和摄取 Worker..."
  exit 0
}

trap cleanup EXIT
trap on_signal INT TERM

if ! command -v uv >/dev/null 2>&1; then
  error "缺少 uv，请先安装并执行 uv sync。"
  exit 1
fi

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  error "缺少 .env，请先执行 cp .env.example .env 并填写模型配置。"
  exit 1
fi

cd "$ROOT_DIR"
info "启动 FastAPI：http://127.0.0.1:8000"
PYTHONUNBUFFERED=1 uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 &
API_PID=$!

info "启动 Outbox Publisher 和摄取 Worker..."
PYTHONUNBUFFERED=1 uv run python -m app.ingestion.worker &
WORKER_PID=$!

info "后端已启动；按 Ctrl+C 会同时停止两个进程。"
while true; do
  if ! kill -0 "$API_PID" 2>/dev/null; then
    error "FastAPI 已退出，正在停止摄取 Worker。"
    exit 1
  fi
  if ! kill -0 "$WORKER_PID" 2>/dev/null; then
    error "摄取 Worker 已退出，正在停止 FastAPI。"
    exit 1
  fi
  sleep 1
done
