# ☕ Coco Automation — Multi-Channel YouTube Content Platform

Nền tảng quản lý nhiều kênh YouTube phong cách Cozy / Study With Me / ASMR / Pomodoro: mỗi kênh có thương hiệu, nhân vật, nội dung, lịch đăng và thống kê **độc lập**. Chạy trên Ubuntu (PC 8 GB RAM), dashboard truy cập qua trình duyệt trong mạng LAN.

> **Trạng thái: Phase 5 (hoàn tất lộ trình)** — kênh, nhân vật, nội dung, render FFmpeg, YouTube OAuth/upload/lịch đăng, Analytics + **Monitoring, watchdog tự khôi phục, health check, logrotate, giới hạn tài nguyên** ([docs/OPERATIONS.md](docs/OPERATIONS.md)).
> Bộ test cần PostgreSQL thật (`TEST_DATABASE_URL`).
>
> **Nâng cấp từ Phase 3/4:** chạy `scripts/restart.sh` (tự áp dụng migration `0004`–`0005`; nếu đã cài systemd, chạy lại `install.sh --systemd` để có health check/logrotate), rồi **ngắt kết nối và kết nối lại** các kênh YouTube đã nối trước đó nếu Analytics báo thiếu quyền (xem [YOUTUBE_SETUP.md](docs/YOUTUBE_SETUP.md)).

## Cài đặt nhanh trên Windows 10/11 (không cần admin)

```powershell
install-windows.cmd        # nhấp đúp (cần Python 3.10+): tự tạo database riêng, FFmpeg đóng gói sẵn
coco start                 # một lệnh khởi chạy toàn bộ; mở http://localhost:8080
```
Lệnh khác: `coco stop | restart | status | logs | backup | restore | autostart on | firewall` — chi tiết: [docs/WINDOWS.md](docs/WINDOWS.md).
Tạo gói chép sang máy khác: `scripts\windows\make-package.ps1`.

## Cài đặt nhanh (Ubuntu 22.04 / 24.04)

```bash
cd coco-automation
./scripts/install.sh --systemd     # cài gói, PostgreSQL, venv, build dashboard, tạo .env, systemd
./scripts/start.sh                 # một lệnh khởi chạy toàn bộ hệ thống
```

Mở `http://<ip-máy>:8080` — đăng nhập `admin` / mật khẩu in ra khi cài (lưu trong `.env`).

| Lệnh | Tác dụng |
|---|---|
| `scripts/start.sh` / `stop.sh` / `restart.sh` / `status.sh` | Điều khiển hệ thống (tự dùng systemd nếu đã cài) |
| `scripts/backup.sh [--db-only]` | Sao lưu DB + file + `.env` vào `backups/` |
| `scripts/restore.sh <file> [--with-env]` | Khôi phục |

Chi tiết: [docs/INSTALL_UBUNTU.md](docs/INSTALL_UBUNTU.md) · [docs/USER_GUIDE.md](docs/USER_GUIDE.md) · [docs/YOUTUBE_SETUP.md](docs/YOUTUBE_SETUP.md) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/OPERATIONS.md](docs/OPERATIONS.md) · [docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md)

## Cấu trúc thư mục

```
coco-automation/
├── backend/                     FastAPI + SQLAlchemy 2 + Alembic
│   ├── app/
│   │   ├── core/                config, database, security (Fernet), storage, logging
│   │   ├── models/              ORM: channel, character, production, ops (16 bảng)
│   │   ├── schemas/             Pydantic request/response
│   │   ├── services/            business logic (channel, character, overview, activity)
│   │   ├── api/routes/          REST endpoints (/api/...)
│   │   └── main.py              app, auth, error handlers, serve SPA + /media
│   ├── alembic/versions/        migrations (0001_initial_schema)
│   ├── tests/                   pytest trên PostgreSQL thật
│   └── requirements.txt
├── frontend/                    React 18 + TypeScript + Vite + Tailwind
│   └── src/{api,components,pages,lib}
├── scripts/                     install / start / stop / restart / status / backup / restore
├── deploy/systemd/              coco-automation.service
├── docs/                        hướng dẫn + schema.sql
├── storage/                     file tải lên & video (theo channels/<id>/...)
└── .env.example
```

## Phát triển

```bash
# backend
cd backend && ../.venv/bin/pip install -r requirements-dev.txt
createdb coco_test   # hoặc đặt TEST_DATABASE_URL
../.venv/bin/pytest -q
../.venv/bin/uvicorn app.main:app --reload --port 8080
# frontend (proxy /api → :8080)
cd frontend && npm install && npm run dev
```

API docs (Swagger): `http://<host>:8080/api/docs`

## Lộ trình

| Phase | Nội dung | Trạng thái |
|---|---|---|
| 1 | Project, Database, Channel Manager, Character Manager, Dashboard cơ bản | ✅ |
| 2 | Content Manager, Asset Manager (licence bắt buộc), Video Generator, FFmpeg render queue | 🟡 code xong, chờ chạy test DB |
| 3 | YouTube OAuth theo từng kênh, upload (mặc định Private), Publishing Scheduler | 🟡 code xong, chờ chạy test DB |
| 4 | YouTube Analytics sync, dashboard thống kê, so sánh hiệu suất | ⏳ |
| 5 | Monitoring, recovery, tối ưu tài nguyên | ⏳ |
| 3D | Cảnh 3D (three.js): xem tương tác trong dashboard + render ra video bằng Chromium không giao diện (không cần GPU) | 🟡 3D-1, 3D-2 xong; 3D-3 (nhân vật phản ứng theo môi trường) chưa làm |
