#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
PID_DIR="$RUNTIME_DIR/pids"
BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"
BACKEND_PORT=8001
FRONTEND_PORT=3008

find_port_pid() {
  local port="$1"
  local pid
  pid="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
  echo "$pid"
  return 0
}

stop_by_pid_file() {
  local name="$1"
  local pid_file="$2"

  if [[ ! -f "$pid_file" ]]; then
    echo "$name is not running (no pid file)"
    return
  fi

  local pid
  pid="$(cat "$pid_file")"

  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "$name stopped (PID: $pid)"
  else
    echo "$name is not running (stale pid file)"
  fi

  rm -f "$pid_file"
}

stop_by_port() {
  local name="$1"
  local port="$2"
  local pid
  pid="$(find_port_pid "$port")"

  if [[ -z "$pid" ]]; then
    echo "$name port $port is not running"
    return
  fi

  kill "$pid" 2>/dev/null || true
  sleep 1
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  echo "$name stopped by port $port (PID: $pid)"
}

stop_by_pid_file "Backend" "$BACKEND_PID_FILE"
stop_by_pid_file "Frontend" "$FRONTEND_PID_FILE"
stop_by_port "Backend" "$BACKEND_PORT"
stop_by_port "Frontend" "$FRONTEND_PORT"
