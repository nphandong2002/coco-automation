# Hướng dẫn cài đặt trên Ubuntu

Yêu cầu: Ubuntu 22.04 hoặc 24.04, user thường có `sudo`, ≥ 8 GB RAM, ổ đĩa trống ≥ 50 GB (video dài rất nặng).

## 1. Cài đặt tự động (khuyến nghị)

```bash
# chép thư mục project lên máy, ví dụ /home/<user>/coco-automation
cd ~/coco-automation
chmod +x scripts/*.sh
./scripts/install.sh --systemd
```

Script sẽ:

1. Cài `python3-venv`, `postgresql`, `ffmpeg`, `curl` (và Node.js 20 nếu Node < 18).
2. Tạo virtualenv `.venv` và cài `backend/requirements.txt`.
3. Tạo `.env` với mật khẩu DB ngẫu nhiên, `SECRET_KEY` Fernet, mật khẩu dashboard ngẫu nhiên (in ra màn hình).
4. Tạo role/database PostgreSQL `coco`.
5. Chạy migration (`alembic upgrade head`) và build dashboard.
6. Cài & enable service `coco-automation` (tự chạy khi khởi động máy).

Khởi chạy: `./scripts/start.sh` → mở `http://<ip-máy>:8080`.

> ⚠️ **Sao lưu file `.env`** (đặc biệt `SECRET_KEY`). Mất key này thì token YouTube đã lưu không giải mã được và phải kết nối lại kênh.

## 2. Truy cập từ máy khác trong mạng LAN

- Lấy IP: `hostname -I`
- Nếu bật UFW: `sudo ufw allow from 192.168.0.0/16 to any port 8080 proto tcp`
- Không mở cổng 8080 ra Internet. Nếu cần truy cập từ xa, dùng VPN (WireGuard/Tailscale).

## 3. Cấu hình (`.env`)

| Biến | Ý nghĩa |
|---|---|
| `PORT` | Cổng dashboard (mặc định 8080) |
| `DATABASE_URL` | Chuỗi kết nối PostgreSQL |
| `SECRET_KEY` | Khóa Fernet mã hóa OAuth token |
| `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD` | Đăng nhập dashboard (để trống password = tắt bảo vệ) |
| `STORAGE_DIR` | Nơi lưu ảnh/âm thanh/video — nên trỏ ổ dữ liệu lớn, ví dụ `/data/coco/storage` |
| `MAX_UPLOAD_MB` | Giới hạn file tải lên |

Sau khi sửa `.env`: `./scripts/restart.sh`.

## 4. Vận hành

```bash
./scripts/start.sh      # khởi chạy (systemd nếu đã cài, nếu không chạy nền với PID file)
./scripts/stop.sh
./scripts/restart.sh
./scripts/status.sh     # trạng thái + /api/health
tail -f logs/app.log logs/server.out
journalctl -u coco-automation -f    # khi chạy bằng systemd
```

## 5. Cài thủ công (khi không dùng install.sh)

```bash
sudo apt install -y python3-venv postgresql ffmpeg nodejs npm
sudo -u postgres createuser -P coco          # nhập mật khẩu
sudo -u postgres createdb -O coco coco
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cp .env.example .env && chmod 600 .env       # điền DATABASE_URL, SECRET_KEY, DASHBOARD_PASSWORD
(cd backend && set -a && . ../.env && ../.venv/bin/alembic upgrade head)
(cd frontend && npm ci && npm run build)
./scripts/start.sh
```

## 6. Cập nhật phiên bản mới

```bash
./scripts/backup.sh
# chép mã nguồn mới đè lên (giữ .env, storage/, backups/)
.venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm ci && npm run build)
./scripts/restart.sh          # run.sh tự chạy migration trước khi khởi động
```

## 7. Xử lý sự cố

| Triệu chứng | Cách xử lý |
|---|---|
| `start.sh` báo không phản hồi sau 30s | Xem `logs/server.out`; thường do PostgreSQL chưa chạy (`sudo systemctl start postgresql`) hoặc sai `DATABASE_URL` |
| Trang trắng / thông báo "Frontend chưa được build" | `cd frontend && npm ci && npm run build` |
| Hỏi mật khẩu liên tục | Kiểm tra `DASHBOARD_USERNAME/PASSWORD` trong `.env` |
| System Settings báo thiếu FFmpeg | `sudo apt install ffmpeg` (bắt buộc từ Phase 2) |
