#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
if systemd_installed; then sudo systemctl restart "$SERVICE"; exec "$APP_DIR/scripts/status.sh"; fi
"$APP_DIR/scripts/stop.sh"
exec "$APP_DIR/scripts/start.sh"
