#!/usr/bin/env bash
# Restore from a backup archive created by backup.sh
#   ./scripts/restore.sh backups/coco-20261109-120000.tar.gz [--with-env]
source "$(dirname "$0")/common.sh"
ARCHIVE="${1:-}"; [[ -f "$ARCHIVE" ]] || die "Cách dùng: restore.sh <file.tar.gz> [--with-env]"
WITH_ENV=0; [[ "${2:-}" == "--with-env" ]] && WITH_ENV=1
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
tar -xzf "$ARCHIVE" -C "$WORK"
[[ -f "$WORK/database.dump" ]] || die "Archive không hợp lệ (thiếu database.dump)"
if [[ $WITH_ENV -eq 1 ]]; then cp "$WORK/env.backup" "$APP_DIR/.env"; chmod 600 "$APP_DIR/.env"; info "Đã khôi phục .env"; fi
load_env
read -r -p "Khôi phục sẽ GHI ĐÈ dữ liệu hiện tại. Gõ 'yes' để tiếp tục: " OK
[[ "$OK" == "yes" ]] || die "Đã hủy."
"$APP_DIR/scripts/stop.sh" || true
PG_URL="${DATABASE_URL/postgresql+psycopg/postgresql}"
info "Khôi phục database..."
pg_restore --clean --if-exists --no-owner --dbname="$PG_URL" "$WORK/database.dump"
if [[ -d "$WORK/storage" ]]; then
  STORAGE="${STORAGE_DIR:-$APP_DIR/storage}"
  info "Khôi phục storage → $STORAGE"
  mkdir -p "$STORAGE"
  cp -a "$WORK/storage/." "$STORAGE/"
fi
info "Xong. Chạy ./scripts/start.sh"
