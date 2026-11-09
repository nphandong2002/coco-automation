# Sao lưu & khôi phục

## Sao lưu

```bash
./scripts/backup.sh            # DB + storage (ảnh, âm thanh, video) + .env
./scripts/backup.sh --db-only  # chỉ DB + .env (nhanh, nhỏ)
```

Tạo `backups/coco-YYYYmmdd-HHMMSS.tar.gz` (quyền 600) gồm:

- `database.dump` — `pg_dump --format=custom`
- `env.backup` — bản sao `.env` (chứa `SECRET_KEY`, mật khẩu)
- `storage/` — toàn bộ file (trừ khi `--db-only`)

**Lịch tự động** (DB hằng đêm 02:30, giữ 14 bản):

```bash
crontab -e
30 2 * * * /home/<user>/coco-automation/scripts/backup.sh --db-only >> /home/<user>/coco-automation/logs/backup.log 2>&1
45 2 * * * find /home/<user>/coco-automation/backups -name 'coco-*.tar.gz' -mtime +14 -delete
```

Video thành phẩm rất lớn: nên sao lưu storage định kỳ sang ổ khác (`rsync -a storage/ /mnt/backup/coco-storage/`) thay vì nén mỗi ngày.

## Khôi phục

```bash
./scripts/restore.sh backups/coco-20261109-120000.tar.gz             # giữ .env hiện tại
./scripts/restore.sh backups/coco-20261109-120000.tar.gz --with-env  # khôi phục cả .env (máy mới)
./scripts/start.sh
```

Script dừng hệ thống, hỏi xác nhận `yes`, chạy `pg_restore --clean`, chép lại `storage/`.

### Chuyển sang máy mới

1. Máy mới: chép mã nguồn, chạy `./scripts/install.sh --systemd`.
2. Chép file backup sang, chạy `restore.sh <file> --with-env`.
3. Nếu `.env` khôi phục có mật khẩu DB khác với máy mới: đặt lại bằng
   `sudo -u postgres psql -c "ALTER ROLE coco PASSWORD '<mật khẩu trong .env>'"`.
4. `./scripts/start.sh`.

> Luôn giữ ít nhất một bản `.env` ngoài máy chủ. Thiếu `SECRET_KEY` đúng thì token YouTube không giải mã được.
