#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
RUNTIME_DIR="$ROOT_DIR/.runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PID_DIR="$RUNTIME_DIR/pids"
BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"
BACKEND_LOG_FILE="$LOG_DIR/backend.log"
FRONTEND_LOG_FILE="$LOG_DIR/frontend.log"
BACKEND_PORT=8001
FRONTEND_PORT=3008

mkdir -p "$LOG_DIR" "$PID_DIR"

is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

find_backend_python() {
  local candidates=("${PYTHON_BIN:-}" python3.11 python3 python3.12 python3.13)
  local py
  for py in "${candidates[@]}"; do
    if [[ -z "$py" ]]; then
      continue
    fi
    if command -v "$py" >/dev/null 2>&1; then
      if "$py" -c 'import uvicorn' >/dev/null 2>&1; then
        echo "$py"
        return 0
      fi
    fi
  done
  return 1
}

find_port_pid() {
  local port="$1"
  local pid
  pid="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
  echo "$pid"
  return 0
}

start_backend() {
  if [[ -f "$BACKEND_PID_FILE" ]]; then
    local pid
    pid="$(cat "$BACKEND_PID_FILE")"
    if is_running "$pid"; then
      echo "Backend already running (PID: $pid)"
      return
    fi
    rm -f "$BACKEND_PID_FILE"
  fi

  local port_pid
  port_pid="$(find_port_pid "$BACKEND_PORT")"
  if [[ -n "$port_pid" ]]; then
    echo "$port_pid" > "$BACKEND_PID_FILE"
    echo "Backend already running on port $BACKEND_PORT (PID: $port_pid)"
    return
  fi

  local backend_python
  backend_python="$(find_backend_python)" || {
    echo "Failed to find a Python interpreter with uvicorn installed"
    exit 1
  }

  (
    cd "$BACKEND_DIR"
    nohup "$backend_python" -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" > "$BACKEND_LOG_FILE" 2>&1 &
    echo $! > "$BACKEND_PID_FILE"
  )

  sleep 2
  if [[ -f "$BACKEND_PID_FILE" ]] && is_running "$(cat "$BACKEND_PID_FILE")"; then
    echo "Backend started: http://127.0.0.1:$BACKEND_PORT"
  else
    echo "Failed to start backend. Check log: $BACKEND_LOG_FILE"
    exit 1
  fi
}

start_frontend() {
  if [[ -f "$FRONTEND_PID_FILE" ]]; then
    local pid
    pid="$(cat "$FRONTEND_PID_FILE")"
    if is_running "$pid"; then
      echo "Frontend already running (PID: $pid)"
      return
    fi
    rm -f "$FRONTEND_PID_FILE"
  fi

  local port_pid
  port_pid="$(find_port_pid "$FRONTEND_PORT")"
  if [[ -n "$port_pid" ]]; then
    echo "$port_pid" > "$FRONTEND_PID_FILE"
    echo "Frontend already running on port $FRONTEND_PORT (PID: $port_pid)"
    return
  fi

  (
    cd "$FRONTEND_DIR"
    nohup npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" > "$FRONTEND_LOG_FILE" 2>&1 &
    echo $! > "$FRONTEND_PID_FILE"
  )

  sleep 2
  if [[ -f "$FRONTEND_PID_FILE" ]] && is_running "$(cat "$FRONTEND_PID_FILE")"; then
    echo "Frontend started: http://127.0.0.1:$FRONTEND_PORT"
  else
    echo "Failed to start frontend. Check log: $FRONTEND_LOG_FILE"
    exit 1
  fi
}

start_backend
start_frontend

echo "Logs:"
echo "  Backend:  $BACKEND_LOG_FILE"
echo "  Frontend: $FRONTEND_LOG_FILE"
