#!/usr/bin/env bash
# Foreground supervisor (used by systemd and start.sh): migrations, then API + render + publish + analytics workers.
# One command starts everything; stopping this script (SIGTERM) stops all three gracefully.
source "$(dirname "$0")/common.sh"
load_env
[[ -x "$VENV/bin/python" ]] || die "Thiếu virtualenv. Chạy scripts/install.sh"
cd "$APP_DIR/backend"
info "Áp dụng database migrations..."
"$VENV/bin/alembic" upgrade head
if [[ ! -f "$APP_DIR/frontend/dist/index.html" ]]; then
  warn "Frontend chưa build — dashboard sẽ không hiển thị. Chạy: cd frontend && npm ci && npm run build"
fi

PIDS=()
# Background workers restart themselves 5 s after an unexpected exit; TERM stops the worker gracefully
# (the render worker re-queues its running job, the publish worker keeps its resumable upload session).
supervise() {
  local kind="$1"
  (
    child=""
    trap 'if [[ -n "$child" ]]; then kill -TERM "$child" 2>/dev/null; wait "$child" 2>/dev/null; fi; exit 0' TERM INT
    while true; do
      "$VENV/bin/python" -m app.worker --kind "$kind" &
      child=$!
      wait "$child"
      warn "Worker '$kind' dừng (mã $?), khởi động lại sau 5s"
      sleep 5 & wait $!
    done
  ) &
  PIDS+=($!)
}

shutdown() {
  trap - TERM INT
  info "Đang dừng hệ thống..."
  kill -TERM "$API_PID" "${PIDS[@]}" 2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}
trap shutdown TERM INT

supervise render
supervise publish
supervise analytics
supervise monitor
info "Khởi chạy Coco Automation tại http://${HOST:-0.0.0.0}:$PORT (API + render + publish + analytics + monitor)"
# Single uvicorn worker on purpose: heavy rendering is serialized (8 GB RAM host).
"$VENV/bin/uvicorn" app.main:app --host "${HOST:-0.0.0.0}" --port "$PORT" --workers 1 \
  --proxy-headers --timeout-graceful-shutdown 30 &
API_PID=$!
wait "$API_PID"
warn "API đã dừng"
shutdown
