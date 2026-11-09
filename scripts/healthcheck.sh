#!/usr/bin/env bash
# Called every minute by coco-healthcheck.timer (or cron). Restarts the service after 3 consecutive failures.
#   exit 0 = healthy   exit 1 = unhealthy (restart triggered when systemd is installed)
source "$(dirname "$0")/common.sh"
load_env
STATE="$RUN_DIR/healthcheck.fails"
if curl -fsS -m 10 -o /dev/null "http://127.0.0.1:$PORT/api/health"; then
  rm -f "$STATE"; exit 0
fi
fails=$(( $(cat "$STATE" 2>/dev/null || echo 0) + 1 ))
echo "$fails" > "$STATE"
warn "Health check thất bại ($fails/3)"
if (( fails >= 3 )); then
  rm -f "$STATE"
  echo "$(date -Is) API không phản hồi 3 lần liên tiếp -> khởi động lại" >> "$APP_DIR/logs/healthcheck.log"
  if systemd_installed; then sudo -n systemctl restart "$SERVICE" || warn "Không có quyền restart (cần sudoers cho systemctl restart $SERVICE)"; fi
fi
exit 1
