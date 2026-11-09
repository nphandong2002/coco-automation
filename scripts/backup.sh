#!/usr/bin/env bash
# Backup database + uploaded/generated files + .env into backups/coco-<timestamp>.tar.gz
#   ./scripts/backup.sh               full backup (DB + storage)
#   ./scripts/backup.sh --db-only     only database + .env (fast, small)
source "$(dirname "$0")/common.sh"
load_env
DB_ONLY=0; [[ "${1:-}" == "--db-only" ]] && DB_ONLY=1
TS=$(date +%Y%m%d-%H%M%S)
OUT_DIR="$APP_DIR/backups"; mkdir -p "$OUT_DIR"
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
PG_URL="${DATABASE_URL/postgresql+psycopg/postgresql}"
info "Dump PostgreSQL..."
pg_dump --format=custom --no-owner --file="$WORK/database.dump" "$PG_URL"
cp "$APP_DIR/.env" "$WORK/env.backup"
STORAGE="${STORAGE_DIR:-$APP_DIR/storage}"
ARGS=(-C "$WORK" database.dump env.backup)
if [[ $DB_ONLY -eq 0 && -d "$STORAGE" ]]; then
  info "Đóng gói storage ($STORAGE)..."
  # always stored as "storage/" inside the archive, whatever STORAGE_DIR is
  ARGS+=(--transform "s,^$(basename "$STORAGE"),storage," -C "$(dirname "$STORAGE")" "$(basename "$STORAGE")")
fi
tar -czf "$OUT_DIR/coco-$TS.tar.gz" "${ARGS[@]}"
chmod 600 "$OUT_DIR/coco-$TS.tar.gz"
info "Đã tạo $OUT_DIR/coco-$TS.tar.gz ($(du -h "$OUT_DIR/coco-$TS.tar.gz" | cut -f1))"
info "Lưu ý: file chứa .env (SECRET_KEY). Cất giữ an toàn."
