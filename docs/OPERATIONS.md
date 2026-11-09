# Vận hành, giám sát & khôi phục (Phase 5)

## 1. Các tiến trình

`scripts/run.sh` (do systemd hoặc `start.sh` chạy) giám sát 5 tiến trình; worker nào thoát bất ngờ sẽ được khởi động lại sau 5 giây.

| Tiến trình | Vai trò | Khóa duy nhất (advisory lock) |
|---|---|---|
| API (uvicorn, 1 worker) | Dashboard + REST | — |
| `render` | Hàng đợi FFmpeg — **1 render nặng/lần** | 72700001 |
| `publish` | Upload YouTube — 1 video/lần | 72700002 |
| `analytics` | Đồng bộ YouTube Analytics | 72700003 |
| `monitor` | Lấy mẫu số đo mỗi phút, watchdog, dọn dẹp mỗi giờ | 72700004 |

Mỗi worker giữ khóa PostgreSQL → không bao giờ có hai bản chạy song song, kể cả khi lỡ chạy `start.sh` hai lần.

## 2. Trang Monitoring

Menu **Monitoring** (tự làm mới 10 giây): CPU, RAM, ổ đĩa lưu video, database (độ trễ, dung lượng, số kết nối),
lịch sử tài nguyên (1 giờ – 7 ngày), trạng thái từng worker, hàng đợi render/upload/analytics, tiến trình FFmpeg đang chạy,
sức khỏe YouTube (kênh cần kết nối lại, lỗi API 24 giờ, lỗi đồng bộ, chờ quota). Mọi số đều đo thật bằng `psutil`/SQL.

Banner trạng thái = mức nặng nhất trong các cảnh báo:

| Mã cảnh báo | Mức | Khi nào | Cách xử lý |
|---|---|---|---|
| `database_down` | nghiêm trọng | DB không phản hồi | `sudo systemctl status postgresql` |
| `disk_critical` / `disk_low` | nghiêm trọng / cảnh báo | trống < `MIN_FREE_DISK_GB` (5) / < `DISK_WARN_GB` (15) | xóa video cũ, thêm dung lượng |
| `ram_high`, `render_waiting_ram` | cảnh báo | RAM > 90% / trống < `MIN_FREE_RAM_MB` khi có render chờ | đóng ứng dụng khác |
| `worker_<loại>_offline` | cảnh báo; **nghiêm trọng** nếu có tác vụ đang chờ | mất heartbeat > 180 s hoặc chưa chạy | `scripts/restart.sh`, `journalctl -u coco-automation` |
| `render_stalled`, `publish_stalled`, `analytics_stalled` | nghiêm trọng | tác vụ treo (xem mục 3) | watchdog tự xử lý ≤ 1 phút |
| `multiple_ffmpeg` | cảnh báo | > 1 FFmpeg cùng chạy | thường là tiến trình mồ côi, dọn dẹp xử lý |
| `youtube_reconnect`, `analytics_sync_error` | cảnh báo | token bị thu hồi / lỗi đồng bộ | kết nối lại kênh |
| `render_failures`, `upload_failures` | cảnh báo | có tác vụ lỗi trong 24 giờ | xem Video Production / Publishing |
| `no_secret_key`, `no_ffmpeg` | nghiêm trọng / cảnh báo | thiếu cấu hình | xem `.env`, `apt install ffmpeg` |

Màn hình Overview hiện một dải cảnh báo khi trạng thái không phải *OK*. `scripts/status.sh` in cùng thông tin trên terminal.

## 3. Khôi phục (recovery)

| Sự cố | Cơ chế | Kết quả |
|---|---|---|
| Mất điện / `kill -9` / máy khởi động lại | Worker khởi động → giữ khóa → mọi tác vụ `RUNNING` là của worker đã chết | Render: xếp lại hàng (tối đa `max_attempts`, quá thì *failed*); upload: **tiếp tục từ byte YouTube đã nhận**, không upload trùng; analytics: xếp lại; file tạm của render bị xóa |
| Worker còn sống nhưng **treo** | Watchdog (monitor worker, mỗi phút): render không heartbeat > 180 s hoặc quá `timeout + 5 phút`; upload không tiến triển > `PUBLISH_STALL_SECONDS`; analytics quá timeout | Gửi SIGTERM (rồi SIGKILL sau 20 s) tới worker **và FFmpeg con** → supervisor khởi động lại → khôi phục như dòng trên. Ghi log `watchdog` mức error |
| FFmpeg mồ côi (worker chết, FFmpeg còn chạy) | Dọn dẹp mỗi giờ: FFmpeg dùng thư mục storage của ta mà không còn tiến trình cha | Bị dừng |
| API treo/không phản hồi | `coco-healthcheck.timer` gọi `/api/health` mỗi phút; 3 lần thất bại liên tiếp | `systemctl restart coco-automation` (ghi `logs/healthcheck.log`) |
| Service crash lặp | `Restart=always`, `StartLimitBurst=5` trong 10 phút | Sau 5 lần: `sudo systemctl reset-failed coco-automation && scripts/start.sh` |
| RAM cạn | Render worker **không bắt đầu** job khi RAM trống < `MIN_FREE_RAM_MB`; `MemoryHigh=5G`, `MemoryMax=6G`, `OOMScoreAdjust=300` | Job chờ tới khi đủ RAM; nếu OOM, kernel ưu tiên dừng service này (không phải ssh/desktop) rồi systemd khởi động lại và khôi phục |
| Đĩa đầy | Render từ chối khi trống < `MIN_FREE_DISK_GB` | Tác vụ lỗi rõ ràng, không làm hỏng video khác |
| Kênh lỗi (token thu hồi, quota, thiếu quyền) | Chỉ ghi vào kênh đó | Kênh khác tiếp tục bình thường |

Watchdog chỉ dừng tiến trình có dòng lệnh chứa `app.worker` và cùng máy → không bao giờ dừng nhầm tiến trình khác khi PID bị tái sử dụng.
Có thể chạy tay: Monitoring → **Kiểm tra tác vụ treo**.

## 4. Dọn dẹp tự động (mỗi giờ, hoặc nút **Dọn dẹp ngay**)

- `system_logs` cũ hơn `LOG_RETENTION_DAYS` (90), `system_metrics` cũ hơn `METRICS_RETENTION_DAYS` (7).
- Dòng `worker_status` đã dừng > 1 ngày, `scheduler_jobs` đã xong > 30 ngày.
- File tạm render (`storage/tmp`) cũ hơn 24 giờ — **bỏ qua khi đang có render chạy**.
- FFmpeg mồ côi.
- Log: `logs/app.log` tự xoay vòng (10 MB × 5); `logs/server.out`, `logs/backup.log` do logrotate (`/etc/logrotate.d/coco-automation`) xoay hàng tuần/20 MB, giữ 8 bản nén.

## 5. Tối ưu cho máy 8 GB

- Chỉ **1** render FFmpeg, **1** upload, **1** đồng bộ analytics tại một thời điểm (khóa advisory trong DB).
- FFmpeg chạy `nice 10`, số luồng = số nhân − 1 (`RENDER_THREADS`), preset `veryfast`, bitrate trần 4500 kbps (`RENDER_*` trong `.env`).
- Upload đọc video theo khối 8 MB, không nạp cả file vào RAM; asset lớn ghi thẳng xuống đĩa.
- Chỉ 1 tiến trình API uvicorn; giới hạn bộ nhớ bằng systemd (`MemoryHigh/Max`).
- Nên để PostgreSQL `shared_buffers` ~256 MB trên máy dùng chung với render.

## 6. systemd (cài bởi `install.sh --systemd`)

```bash
sudo systemctl status coco-automation
systemctl list-timers coco-healthcheck.timer      # health check mỗi phút
sudo systemctl reset-failed coco-automation       # sau khi service bị giới hạn khởi động lại
journalctl -u coco-automation -n 200 --no-pager
tail -f logs/healthcheck.log
```

Nâng cấp từ Phase 4 mà đã cài systemd: chạy lại `./scripts/install.sh --systemd` (không ghi đè `.env`) để cài timer, logrotate và unit mới, rồi `./scripts/restart.sh`.
