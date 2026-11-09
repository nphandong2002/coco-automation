#!/usr/bin/env bash
# Start the whole system with one command.
source "$(dirname "$0")/common.sh"
load_env
if systemd_installed; then
  info "Khởi động qua systemd ($SERVICE)..."
  sudo systemctl start "$SERVICE"
else
  if is_running_pid; then info "Đang chạy (PID $(cat "$PID_FILE"))."; exit 0; fi
  # Make sure PostgreSQL is up when it is a local service
  if has_systemd && systemctl list-unit-files postgresql.service >/dev/null 2>&1; then
    systemctl is-active --quiet postgresql 2>/dev/null || sudo systemctl start postgresql || true
  fi
  nohup "$APP_DIR/scripts/run.sh" >>"$APP_DIR/logs/server.out" 2>&1 &
  echo $! > "$PID_FILE"
fi
# wait for health
for _ in $(seq 1 30); do
  if curl -fs -o /dev/null "http://127.0.0.1:$PORT/api/health"; then
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    info "Sẵn sàng: http://localhost:$PORT  (mạng LAN: http://${IP:-<ip-may>}:$PORT)"
    exit 0
  fi
  sleep 1
done
die "Server chưa phản hồi sau 30s. Xem logs/server.out hoặc: journalctl -u $SERVICE -n 100"
