#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

bash "$ROOT_DIR/stop_app.sh"
sleep 1
bash "$ROOT_DIR/start_app.sh"
