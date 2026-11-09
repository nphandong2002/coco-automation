#!/usr/bin/env bash
# Coco Automation installer for Ubuntu 22.04 / 24.04.
#   ./scripts/install.sh              install everything, run with start.sh
#   ./scripts/install.sh --systemd    also install & enable the systemd service (auto start on boot)
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WITH_SYSTEMD=0; [[ "${1:-}" == "--systemd" ]] && WITH_SYSTEMD=1
info() { echo -e "\033[1;32m[install]\033[0m $*"; }
die()  { echo -e "\033[1;31m[install]\033[0m $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] && die "Đừng chạy bằng root. Chạy bằng user thường có quyền sudo."

info "1/7 Cài gói hệ thống (python3, postgresql, ffmpeg, curl)..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip postgresql postgresql-contrib ffmpeg curl ca-certificates

info "2/7 Kiểm tra Node.js (cần >= 18 để build dashboard)..."
NODE_MAJOR=$(node -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/' || echo 0)
if [[ "${NODE_MAJOR:-0}" -lt 18 ]]; then
  info "Cài Node.js 20 LTS từ NodeSource..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

info "3/7 Tạo Python virtualenv..."
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip wheel >/dev/null
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt"

info "4/7 Tạo file .env..."
if [[ ! -f "$APP_DIR/.env" ]]; then
  DB_PASS=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
  SECRET=$("$APP_DIR/.venv/bin/python" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
  DASH_PASS=$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')
  sed -e "s#CHANGE_ME#$DB_PASS#" -e "s#^SECRET_KEY=.*#SECRET_KEY=$SECRET#" \
      -e "s#^DASHBOARD_PASSWORD=.*#DASHBOARD_PASSWORD=$DASH_PASS#" "$APP_DIR/.env.example" > "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "$DB_PASS" > "$APP_DIR/.db_pass.tmp"
  info "Đã tạo .env  —  Dashboard login: admin / $DASH_PASS  (xem/đổi trong .env)"
  info ">>> SAO LƯU file .env (đặc biệt SECRET_KEY) ở nơi an toàn <<<"
fi

info "5/7 Tạo PostgreSQL user & database..."
sudo systemctl enable --now postgresql
if [[ -f "$APP_DIR/.db_pass.tmp" ]]; then
  DB_PASS=$(cat "$APP_DIR/.db_pass.tmp")
  sudo -u postgres psql -v ON_ERROR_STOP=1 >/dev/null <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'coco') THEN
    CREATE ROLE coco LOGIN PASSWORD '$DB_PASS';
  ELSE
    ALTER ROLE coco WITH PASSWORD '$DB_PASS';
  END IF;
END \$\$;
SQL
  sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='coco'" | grep -q 1 || \
    sudo -u postgres createdb -O coco coco
  rm -f "$APP_DIR/.db_pass.tmp"
fi

info "6/7 Migrate database & build dashboard..."
( cd "$APP_DIR/backend" && set -a && source "$APP_DIR/.env" && set +a && "$APP_DIR/.venv/bin/alembic" upgrade head )
( cd "$APP_DIR/frontend" && npm ci --no-audit --no-fund && npm run build )
mkdir -p "$APP_DIR/storage" "$APP_DIR/logs" "$APP_DIR/backups"
chmod +x "$APP_DIR"/scripts/*.sh

if [[ $WITH_SYSTEMD -eq 1 ]]; then
  info "7/7 Cài systemd service..."
  sed -e "s#__APP_DIR__#$APP_DIR#g" -e "s#__USER__#$USER#g" \
    "$APP_DIR/deploy/systemd/coco-automation.service" | sudo tee /etc/systemd/system/coco-automation.service >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable coco-automation
  # Phase 5: health check timer (restarts the service if the API hangs), log rotation, restart permission
  for u in coco-healthcheck.service coco-healthcheck.timer; do
    sed -e "s#__APP_DIR__#$APP_DIR#g" -e "s#__USER__#$USER#g" "$APP_DIR/deploy/systemd/$u"       | sudo tee "/etc/systemd/system/$u" >/dev/null
  done
  sed -e "s#__APP_DIR__#$APP_DIR#g" "$APP_DIR/deploy/logrotate/coco-automation"     | sudo tee /etc/logrotate.d/coco-automation >/dev/null
  echo "$USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart coco-automation, /usr/bin/systemctl start coco-automation, /usr/bin/systemctl stop coco-automation"     | sudo tee /etc/sudoers.d/coco-automation >/dev/null
  sudo chmod 440 /etc/sudoers.d/coco-automation
  sudo systemctl daemon-reload
  sudo systemctl enable coco-healthcheck.timer
  info "Đã bật tự khởi động cùng hệ thống."
else
  info "7/7 Bỏ qua systemd (chạy lại với --systemd để tự khởi động khi boot)."
fi
info "Hoàn tất! Khởi chạy: ./scripts/start.sh"
