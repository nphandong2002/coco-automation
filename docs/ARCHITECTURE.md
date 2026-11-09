# Kiến trúc hệ thống

## 1. Tổng quan

```
Trình duyệt (LAN) ──HTTP──▶ Uvicorn (1 process)
                             ├── /            React SPA (frontend/dist)
                             ├── /api/*       FastAPI routers → services → SQLAlchemy
                             └── /media/*     file trong storage/
                                   │
                    PostgreSQL ◀───┘           storage/channels/<id>/...
                                               (Phase 2+) Worker: render queue (FFmpeg, 1 job nặng),
                                               upload queue, scheduler, analytics sync
```

Một tiến trình web duy nhất + (từ Phase 2) **một worker** riêng lấy job từ bảng `video_jobs` / `scheduler_jobs` / `publishing_jobs`. Hàng đợi nằm trong PostgreSQL nên **không mất khi restart**; worker dùng `SELECT … FOR UPDATE SKIP LOCKED`, `dedupe_key` và heartbeat để không chạy trùng và tự thu hồi job treo.

## 2. Phân lớp backend

| Lớp | Thư mục | Vai trò |
|---|---|---|
| Core | `app/core` | cấu hình `.env`, engine DB, mã hóa Fernet, lưu file (content-addressed), logging xoay vòng |
| Models | `app/models` | 16 bảng, ràng buộc, enum dạng VARCHAR+CHECK |
| Schemas | `app/schemas` | validate input (mã kênh, múi giờ IANA, HEX màu, HH:MM…) |
| Services | `app/services` | toàn bộ business rule; ném `AppError` → HTTP code |
| API | `app/api/routes` | mỏng, chỉ gọi service |

## 3. Cô lập dữ liệu giữa các kênh

1. **Mọi bảng nghiệp vụ có `channel_id`** (FK `ON DELETE CASCADE`).
2. **Khóa ngoại phức hợp** chặn tham chiếu chéo ngay ở DB:
   - `content_projects (channel_id, character_id)` → `channel_characters (channel_id, character_id)`: nội dung chỉ dùng được nhân vật **thuộc hoặc được cấp quyền** cho kênh đó.
   - `content_projects (character_id, character_version_id)` → `character_versions (character_id, id)`: phiên bản phải thuộc đúng nhân vật.
   - `video_jobs`, `videos` → `content_projects (channel_id, id)`; `publishing_jobs`, `analytics_video` → `videos (channel_id, id)`.
3. **API luôn scope theo kênh**: `/api/channels/{channel_id}/characters/{id}`. Kênh không có quyền nhận 404 (không lộ sự tồn tại).
4. **File** lưu theo `storage/channels/<channel_id>/…`; xóa kênh xóa thư mục của kênh.
5. **OAuth** mỗi kênh một dòng `youtube_credentials` (UNIQUE channel_id), token mã hóa Fernet (`EncryptedJSON`).
6. **Lỗi của một kênh** chỉ ghi vào `channels.last_error` của kênh đó → trạng thái `Error`, các kênh khác không bị ảnh hưởng. Worker (Phase 2+) bắt lỗi theo từng job.

## 4. Trạng thái kênh (tính toán, không lưu cứng)

| Ưu tiên | Điều kiện | Trạng thái |
|---|---|---|
| 1 | `enabled = false` | **Paused** |
| 2 | `last_error` khác rỗng | **Error** |
| 3 | không có credential hợp lệ | **Disconnected** |
| 4 | còn lại | **Active** |

Vì thế kênh mới tạo hiển thị *Disconnected* cho tới khi kết nối YouTube (Phase 3) — đúng sự thật, không giả lập.

## 5. Nhân vật & tính nhất quán

- `characters`: danh tính (tên, loài, kênh sở hữu, `current_version_id`).
- `character_versions`: **bất biến**. Mọi thay đổi ngoại hình / ảnh / biểu cảm / ảnh tham chiếu tạo phiên bản mới (sao chép phiên bản hiện tại + phần thay đổi). Thao tác không thay đổi gì bị từ chối.
- Có thể "dùng lại" phiên bản cũ (rollback) — chỉ đổi con trỏ, không sửa lịch sử.
- Ảnh lưu theo SHA-256 → nhiều phiên bản dùng chung file, không trùng lặp.
- `channel_characters`: quyền sử dụng + vai trò (chính/phụ) **theo từng kênh**. Kênh sở hữu luôn có 1 dòng `is_owner=true`. Kênh khác chỉ dùng được khi chủ sở hữu cấp quyền; kênh được cấp quyền chỉ đọc. Index duy nhất có điều kiện đảm bảo **tối đa 1 nhân vật chính / kênh**.
- Phase 2: `content_projects` ghim `character_version_id` → video render lại sau này vẫn đúng ngoại hình.

## 6. Database (16 bảng)

| Nhóm | Bảng |
|---|---|
| Kênh | `channels`, `youtube_credentials` |
| Nhân vật | `characters`, `character_versions`, `channel_characters` |
| Nội dung & sản xuất | `content_ideas` (UNIQUE channel+fingerprint chống trùng lặp), `content_projects`, `video_templates`, `assets` (bắt buộc licence), `video_jobs`, `videos` |
| Đăng | `publishing_jobs` (mặc định `private`, retry, resumable upload) |
| Thống kê | `analytics_daily`, `analytics_video` (cột `data_source`: `youtube_api` / `estimated`) |
| Vận hành | `scheduler_jobs` (dedupe_key, timeout, attempts), `system_logs` |

DDL đầy đủ: [schema.sql](schema.sql). Migration: `backend/alembic/versions/`.

**Nguyên tắc số liệu:** dashboard chỉ cộng dữ liệu `data_source='youtube_api'`; khi chưa có dữ liệu trả `{"value": null, "source": "not_synced"}` và UI hiển thị "Chưa đồng bộ" — không bao giờ hiển thị số giả.

## 7. Bảo mật

- Dashboard: HTTP Basic (`DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD`), so sánh hằng thời gian. `/api/health` mở để giám sát.
- `.env` quyền 600; `SECRET_KEY` (Fernet) mã hóa token OAuth.
- Upload: kiểm tra bằng Pillow (PNG/JPEG/WEBP), giới hạn dung lượng, ghi file atomic, chống path traversal.

## 8. Kế hoạch các phase tiếp theo (không đổi kiến trúc)

- **Phase 2**: `services/content_service.py`, `asset_service.py`, `worker/` (process riêng, systemd unit thứ 2), `render/` (timeline → filtergraph FFmpeg, `-threads` giới hạn, `nice`, render 1 job nặng/lần, ffprobe QC sau render).
- **Phase 3**: `integrations/youtube/` (google-auth-oauthlib, upload resumable, thumbnails, playlist), scheduler tạo `publishing_jobs` từ `channels.publish_schedule`.
- **Phase 4**: sync YouTube Analytics API → `analytics_*`, Recharts, so sánh/khuyến nghị dựa trên watch time, AVD, retention, subscriber gained.
- **Phase 5**: trang Monitoring (CPU/RAM/disk/FFmpeg/queue/API errors), recovery job treo, dọn file tạm.
