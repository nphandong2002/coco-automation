# Kết nối YouTube

Mỗi kênh Coco kết nối với **một kênh YouTube riêng** qua OAuth 2.0. Bạn đăng nhập trên trang của Google;
hệ thống chỉ nhận refresh token (mã hóa Fernet bằng `SECRET_KEY` trong bảng `youtube_credentials`). Không dùng
kỹ thuật vượt CAPTCHA/2FA hay né giới hạn API.

## 1. Tạo OAuth client (một lần cho cả hệ thống)

1. Vào <https://console.cloud.google.com/> → tạo project (vd. `coco-automation`).
2. **APIs & Services → Library**: bật **YouTube Data API v3** và **YouTube Analytics API** (Analytics dùng ở Phase 4).
3. **OAuth consent screen**: chọn *External*, điền tên ứng dụng và email. Thêm các scope:
   `youtube.upload`, `youtube`, `yt-analytics.readonly`.
4. **Quan trọng — trạng thái Testing**: ứng dụng ở trạng thái *Testing* chỉ cho phép các *Test users* bạn thêm,
   và **refresh token hết hạn sau 7 ngày** (phải kết nối lại hằng tuần). Với dùng cá nhân, đặt *Publishing status =
   In production* (Google hiện cảnh báo "ứng dụng chưa được xác minh" — chọn *Advanced → Go to …*; dùng được cho tài khoản của bạn).
5. **Credentials → Create credentials → OAuth client ID → Web application**.
   *Authorized redirect URIs*: đúng giá trị `OAUTH_REDIRECT_URI` (mặc định `http://localhost:8080/api/youtube/oauth/callback`).
6. Sao chép Client ID / Client secret vào `.env`:

```bash
GOOGLE_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxxxxxxx
OAUTH_REDIRECT_URI=http://localhost:8080/api/youtube/oauth/callback
```

Khởi động lại: `scripts/restart.sh`.

### Truy cập dashboard từ máy khác trong LAN

Google **không chấp nhận redirect URI dạng `http://192.168.x.x`** (chỉ `localhost` hoặc HTTPS với tên miền). Hai cách:

- **SSH tunnel** (đơn giản): trên máy bạn chạy `ssh -L 8080:localhost:8080 user@<ip-ubuntu>`, rồi mở
  `http://localhost:8080` và bấm *Kết nối YouTube*.
- Hoặc đặt reverse proxy HTTPS với tên miền riêng và đặt `OAUTH_REDIRECT_URI=https://<ten-mien>/api/youtube/oauth/callback`.

Chỉ cần dùng cách này khi **kết nối** kênh; sau đó worker tự làm mới token và upload không cần trình duyệt.

## 2. Kết nối từng kênh

Channels → chọn kênh → tab **YouTube** → **Kết nối YouTube** → chọn đúng tài khoản/kênh sẽ đăng → cho phép.
Một kênh YouTube chỉ gắn được với một kênh Coco. **Ngắt kết nối** sẽ thu hồi và xóa token.
Nếu token bị thu hồi (đổi mật khẩu Google, gỡ quyền…), kênh chuyển sang *Error*, các tác vụ đăng của kênh đó
**chờ** (không mất) cho tới khi bạn kết nối lại; các kênh khác không bị ảnh hưởng.

## 3. Hạn mức (quota) & giới hạn của YouTube

- Mặc định 10.000 đơn vị/ngày cho cả project. Một lần upload (`videos.insert`) tốn ~1.600 đơn vị → **khoảng 6 video/ngày**
  cho tất cả kênh cộng lại. Hết quota, tác vụ tự chờ tới nửa đêm giờ Thái Bình Dương (≈ 14:00 giờ VN) rồi chạy tiếp.
  Cần nhiều hơn: gửi mẫu xin tăng quota trong Google Cloud.
- Project API **chưa qua audit** có thể bị YouTube **khóa video ở chế độ Private** khi upload qua API. Nếu video
  không thể chuyển Public, gửi *YouTube API Services audit* của Google; trong lúc đó bạn có thể đổi công khai thủ công trong YouTube Studio.
- Thumbnail tùy chỉnh yêu cầu kênh đã xác minh số điện thoại. Nếu bị từ chối, video vẫn đăng thành công
  và tác vụ ghi cảnh báo "thumbnail".

## 4. Đăng video

1. Render xong video (qua kiểm tra chất lượng) → **Video Production → Videos** hoặc tab *Video* của kênh → **↑ Đăng YouTube**.
2. Kiểm tra tiêu đề/mô tả/tags (mặc định lấy từ dự án nội dung), chọn playlist, danh mục.
3. Quyền riêng tư mặc định **Private** để kiểm tra trên YouTube trước khi công khai. Có thể chọn Unlisted/Public.
4. **Hẹn giờ công khai**: chọn *Slot trống kế tiếp của kênh* (từ lịch đăng trong cấu hình kênh) hoặc giờ cụ thể.
   Video được upload Private ngay, YouTube tự công khai đúng giờ.
5. Theo dõi ở **Publishing** (tiến độ, lịch sử từng bước, thử lại/hủy) và **Scheduler** (khung giờ + slot trống + video đã hẹn).

Upload chạy nền (một video mỗi lần), tự thử lại với backoff khi lỗi mạng/5xx, và **tiếp tục từ byte đã gửi** sau khi
khởi động lại; ID video YouTube được ghi vào DB ngay sau upload nên không bao giờ upload trùng.

## 5. Xử lý sự cố

| Triệu chứng | Cách xử lý |
|---|---|
| "Chưa cấu hình Google OAuth" | Điền `GOOGLE_CLIENT_ID/SECRET` trong `.env`, `scripts/restart.sh` |
| Google báo `redirect_uri_mismatch` | `OAUTH_REDIRECT_URI` phải trùng *chính xác* URI đã đăng ký |
| `access_denied` / "Error 403: access_denied" | Thêm tài khoản vào *Test users* hoặc chuyển app sang In production |
| Không nhận refresh token | Gỡ quyền tại <https://myaccount.google.com/permissions> rồi kết nối lại |
| Kênh "Cần kết nối lại" | Token bị thu hồi/hết hạn → Kết nối lại; tác vụ đang chờ tự chạy tiếp |
| Tác vụ "Đang chờ" mãi | Kiểm tra *Upload worker* trên trang Publishing; xem `logs/server.out` |
