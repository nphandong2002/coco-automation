#!/usr/bin/env bash
# Foreground runner (used by systemd and start.sh). Applies migrations then starts the API + dashboard.
source "$(dirname "$0")/common.sh"
load_env
[[ -x "$VENV/bin/python" ]] || die "Thiếu virtualenv. Chạy scripts/install.sh"
cd "$APP_DIR/backend"
info "Áp dụng database migrations..."
"$VENV/bin/alembic" upgrade head
if [[ ! -f "$APP_DIR/frontend/dist/index.html" ]]; then
  warn "Frontend chưa build — dashboard sẽ không hiển thị. Chạy: cd frontend && npm ci && npm run build"
fi
info "Khởi chạy Coco Automation tại http://${HOST:-0.0.0.0}:$PORT"
# Single worker on purpose: background jobs/heavy rendering are serialized (8 GB RAM host).
exec "$VENV/bin/uvicorn" app.main:app --host "${HOST:-0.0.0.0}" --port "$PORT" --workers 1 \
  --proxy-headers --timeout-graceful-shutdown 30
