#!/usr/bin/env bash
# Shared helpers for Coco Automation scripts
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$APP_DIR/.venv"
RUN_DIR="$APP_DIR/run"
PID_FILE="$RUN_DIR/coco.pid"
SERVICE="coco-automation"
mkdir -p "$RUN_DIR" "$APP_DIR/logs"

info()  { echo -e "\033[1;32m[coco]\033[0m $*"; }
warn()  { echo -e "\033[1;33m[coco]\033[0m $*"; }
die()   { echo -e "\033[1;31m[coco]\033[0m $*" >&2; exit 1; }

load_env() {
  [[ -f "$APP_DIR/.env" ]] || die ".env không tồn tại. Chạy scripts/install.sh trước."
  set -a; # shellcheck disable=SC1091
  source "$APP_DIR/.env"; set +a
  PORT="${PORT:-8080}"
}

has_systemd() { [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null 2>&1; }

systemd_installed() {
  has_systemd && systemctl list-unit-files "$SERVICE.service" 2>/dev/null | grep -q "$SERVICE"
}

is_running_pid() {
  [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}
