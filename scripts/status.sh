#!/usr/bin/env bash
# Quick status: service, API health, workers, alerts (from /api/monitoring).
source "$(dirname "$0")/common.sh"
load_env
if systemd_installed; then systemctl --no-pager status "$SERVICE" | head -5; fi
if ! curl -fsS "http://127.0.0.1:$PORT/api/health"; then warn "API không phản hồi trên cổng $PORT"; exit 1; fi
echo
AUTH=(); [[ -n "${DASHBOARD_PASSWORD:-}" ]] && AUTH=(-u "${DASHBOARD_USERNAME:-admin}:$DASHBOARD_PASSWORD")
"$VENV/bin/python" - "$PORT" "${AUTH[@]:-}" <<'PY' || true
import json, sys, urllib.request, base64
port, *auth = sys.argv[1:]
req = urllib.request.Request(f"http://127.0.0.1:{port}/api/monitoring")
if len(auth) == 2:
    req.add_header("Authorization", "Basic " + base64.b64encode(auth[1].encode()).decode())
m = json.load(urllib.request.urlopen(req, timeout=15))
h = m["host"]
print(f"Trạng thái: {m['status'].upper()}   CPU {h['cpu_percent']}%  RAM {h['ram_percent']}% (trống {h['ram_available_mb']} MB)  Đĩa trống {h['disk_free_gb']} GB")
for w in m["workers"]:
    print(f"  worker {w['kind']:<10} {'ON ' if w['online'] else 'OFF'} {w['state']}")
q = m["queues"]
print(f"  render chờ/chạy {q['render']['queued']}/{q['render']['running']}  upload chờ/chạy {q['upload']['queued']}/{q['upload']['running']}")
for a in m["alerts"]:
    print(f"  [{a['severity']}] {a['message']}")
PY
