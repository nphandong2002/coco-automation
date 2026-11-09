# Chạy Coco Automation trên Windows 10/11

Bản Windows chạy **toàn bộ** hệ thống (dashboard, render FFmpeg, upload/lịch đăng YouTube, Analytics, Monitoring) trên PC của bạn,
**không cần quyền Administrator, không cần cài PostgreSQL hay FFmpeg riêng**: ứng dụng tự mang theo PostgreSQL riêng (chỉ lắng nghe `127.0.0.1`)
và FFmpeg đóng gói sẵn.

## 1. Yêu cầu

| Thành phần | Ghi chú |
|---|---|
| Windows 10/11 64-bit, RAM ≥ 8 GB, ổ đĩa trống ≥ 50 GB | video dài rất nặng |
| **Python 3.10+** (khuyến nghị 3.12) | `winget install Python.Python.3.12` — tích *Add python.exe to PATH* |
| Node.js 18+ | **chỉ cần** khi cài từ mã nguồn; gói dựng sẵn (mục 2A) không cần |

## 2. Cài đặt

### A. Từ gói dựng sẵn (khuyến nghị)
1. Giải nén `coco-automation-windows.zip` vào một thư mục cố định, ví dụ `D:\coco-automation` (đường dẫn càng ngắn càng tốt).
2. Nhấp đúp **`install-windows.cmd`** (3–5 phút lần đầu: tạo `.venv`, cài thư viện, tạo database, migration).
3. Cuối cùng in ra mật khẩu đăng nhập dashboard — **ghi lại**, và **sao lưu file `.env`** (chứa `SECRET_KEY` mã hóa token YouTube).

### B. Từ mã nguồn (git clone)
```powershell
cd D:\coco-automation
powershell -ExecutionPolicy Bypass -File scripts\windows\install.ps1        # tự build dashboard bằng Node
```
Tùy chọn: `-Port 8080`, `-Autostart` (tự chạy khi đăng nhập Windows), `-Rebuild` (build lại dashboard),
`-ExternalDb "postgresql+psycopg://user:pass@localhost:5432/coco"` (dùng PostgreSQL có sẵn thay cho bản riêng).

Tạo gói để chép sang máy khác: `powershell -File scripts\windows\make-package.ps1` → `dist\coco-automation-windows.zip`.

## 3. Sử dụng — lệnh `coco`

Mở PowerShell/CMD trong thư mục cài đặt:

| Lệnh | Tác dụng |
|---|---|
| `coco start` | **Một lệnh** khởi chạy tất cả (PostgreSQL riêng, migration, API, 4 worker), chạy nền, ẩn cửa sổ |
| `coco stop` | Dừng êm (worker hoàn tất/hoàn trả tác vụ, PostgreSQL tắt sạch) — thường vài giây |
| `coco restart` / `coco status` | Khởi động lại / trạng thái, worker, cảnh báo |
| `coco run` | Chạy ở cửa sổ hiện tại để xem log trực tiếp (Ctrl+C để dừng) |
| `coco logs` / `coco open` | Theo dõi `logs\app.log` / mở dashboard trong trình duyệt |
| `coco backup [-DbOnly]` | Tạo `backups\coco-<ngày>.zip` (database + storage + `.env`) |
| `coco restore <file.zip> [-WithEnv] [-Yes]` | Khôi phục (tự dừng hệ thống trước). `-WithEnv` lấy `SECRET_KEY` từ bản sao lưu nhưng **giữ** `DATABASE_URL` của máy này |
| `coco autostart on\|off` | Tự chạy khi đăng nhập Windows (Task Scheduler, không cần admin) |
| `coco firewall` | Cho máy khác trong **mạng LAN riêng** vào dashboard (cần mở PowerShell bằng *Run as administrator*) |

Dashboard: `http://localhost:8080` (cổng theo `PORT` trong `.env`). Đăng nhập `admin` + mật khẩu in lúc cài (xem `.env`).
Xem LAN: `coco start` in địa chỉ `http://<ip>:8080`; lần đầu Windows có thể hỏi cho phép Python qua tường lửa → chọn **Private networks**.

## 4. Kết nối YouTube, tạo kênh, render, lên lịch, Analytics

Giống bản Ubuntu — xem [USER_GUIDE.md](USER_GUIDE.md) và [YOUTUBE_SETUP.md](YOUTUBE_SETUP.md).
Khác biệt duy nhất: redirect URI mặc định `http://localhost:<PORT>/api/youtube/oauth/callback` (mở dashboard bằng `localhost` trên chính PC này khi bấm *Kết nối YouTube*).

## 5. Cách hoạt động trên Windows

- `coco start` chạy `python -m app.tools.supervisor` (thay `scripts/run.sh`): bật PostgreSQL riêng (`data\pgdata`, cổng 54329), chạy migration, rồi giám sát API + `render`, `publish`, `analytics`, `monitor`.
  Tiến trình nào chết sẽ được chạy lại sau 5 giây; API không phản hồi `/api/health` 3 lần liên tiếp (mỗi 30 giây) sẽ được khởi động lại.
- Dừng êm bằng `Ctrl+Break` tới từng worker (Windows không có SIGTERM); quá 60 giây mới buộc dừng. Tác vụ dở dang được khôi phục lần chạy sau (xem [OPERATIONS.md](OPERATIONS.md)): render xếp lại hàng, upload **tiếp tục từ byte YouTube đã nhận**.
- FFmpeg: dùng `ffmpeg` trong PATH nếu có, nếu không dùng bản đóng gói (`FFMPEG_PATH` trong `.env`); chạy mức ưu tiên *Below Normal* để PC vẫn dùng được khi render. Font lấy từ `C:\Windows\Fonts`.
- Watchdog, Monitoring, dọn dẹp, giới hạn RAM cho render: như [OPERATIONS.md](OPERATIONS.md) (phần systemd/logrotate chỉ dành cho Ubuntu; Windows dùng supervisor ở trên).
- Dữ liệu: `data\pgdata` (database), `storage\` (ảnh/audio/video), `logs\`, `backups\`, `.env`. Đặt `STORAGE_DIR=E:\coco-storage` trong `.env` để lưu video ở ổ khác.

## 6. Cập nhật phiên bản mới

```powershell
coco backup
coco stop
# chép/ghi đè mã nguồn mới (giữ nguyên .env, data\, storage\, backups\)
powershell -ExecutionPolicy Bypass -File scripts\windows\install.ps1 -Rebuild    # cài thư viện mới + migration + dashboard
coco start
```

## 7. Xử lý sự cố

| Triệu chứng | Cách xử lý |
|---|---|
| `install` báo cần Python | `winget install Python.Python.3.12`, mở cửa sổ PowerShell mới rồi chạy lại |
| `coco start` quá 2 phút không sẵn sàng | `coco run` để thấy lỗi; xem `logs\server.out`, `logs\app.log`, `logs\postgres.log` |
| "Cổng 8080 đang dùng" | Đổi `PORT=` trong `.env` (và `OAUTH_REDIRECT_URI`, URI trong Google Cloud), `coco restart` |
| PowerShell chặn script | Dùng `coco.cmd` (đã kèm `-ExecutionPolicy Bypass`) hoặc nhấp đúp `install-windows.cmd` |
| Máy khác không vào được | Bấm cho phép tường lửa lần đầu, hoặc `coco firewall` (admin); chỉ dùng mạng *Private* |
| PostgreSQL không lên sau khi mất điện | Thường tự phục hồi từ WAL. Nếu `logs\postgres.log` báo lỗi: `coco backup` không được → khôi phục bản sao lưu gần nhất bằng `coco restore` |
| Windows Defender/antivirus chặn | Thêm thư mục cài đặt vào danh sách loại trừ (quét thời gian thực làm chậm render và PostgreSQL) |
| Muốn dùng PostgreSQL có sẵn | Cài với `-ExternalDb "..."`, hoặc sửa `.env`: `EMBEDDED_PG=false` và `DATABASE_URL=...` |

Bảo mật: PostgreSQL riêng chỉ nhận kết nối từ `127.0.0.1`, có mật khẩu ngẫu nhiên (scram-sha-256) trong `.env`. Dashboard có mật khẩu (HTTP Basic); không mở cổng ra Internet — truy cập từ xa bằng VPN (Tailscale/WireGuard).
