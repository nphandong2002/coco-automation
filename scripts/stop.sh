#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
if systemd_installed; then
  info "Dừng qua systemd..."; sudo systemctl stop "$SERVICE"; exit 0
fi
if is_running_pid; then
  PID=$(cat "$PID_FILE"); info "Dừng PID $PID..."
  kill -TERM "$PID"
  for _ in $(seq 1 30); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
  kill -0 "$PID" 2>/dev/null && { warn "Buộc dừng"; kill -KILL "$PID"; }
  rm -f "$PID_FILE"; info "Đã dừng."
else
  rm -f "$PID_FILE"; info "Không có tiến trình nào đang chạy."
fi
