#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
load_env
if systemd_installed; then systemctl --no-pager status "$SERVICE" | head -5; fi
if curl -fsS "http://127.0.0.1:$PORT/api/health"; then echo; else warn "API không phản hồi trên cổng $PORT"; exit 1; fi
