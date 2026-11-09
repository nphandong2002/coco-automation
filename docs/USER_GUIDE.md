# Hướng dẫn sử dụng

## 1. Tạo kênh

1. **Channels → + Thêm kênh**.
2. Nhập *Tên kênh*; *Mã kênh* tự sinh (a-z, 0-9, `-`, không đổi được sau khi tạo).
3. Điền ngôn ngữ, quốc gia mục tiêu, mô tả, chủ đề (phân tách dấu phẩy).
4. **Phong cách hình ảnh**: theme, mood, bảng màu HEX, từ khóa. **Phong cách âm thanh**: ambience, nhạc nền.
5. **Lịch đăng**: múi giờ IANA + các khung giờ theo thứ trong tuần (Scheduler dùng từ Phase 3).
6. **Tạo kênh** → chuyển sang trang chi tiết.

Trang chi tiết kênh có các tab: *Tổng quan* (số liệu từ DB), *Thương hiệu & lịch đăng* (sửa cấu hình, tải avatar/banner), *Nhân vật*, *YouTube* (trạng thái kết nối), *Hoạt động* (nhật ký riêng của kênh).

| Thao tác | Ghi chú |
|---|---|
| ⏸ Tạm dừng / ▶ Bật kênh | Kênh tạm dừng sẽ không được Scheduler xử lý (Phase 3) |
| ⧉ Sao chép | Tạo kênh mới với cùng cấu hình thương hiệu, lịch đăng, avatar/banner, tùy chọn sao chép **nhân vật do kênh sở hữu** thành bản độc lập. Không sao chép kết nối YouTube, video, thống kê, nhân vật được cấp quyền |
| Xóa | Phải gõ đúng mã kênh. Xóa toàn bộ dữ liệu & file của kênh. Bị chặn nếu nhân vật của kênh đang được kênh khác dùng trong nội dung |
| Đánh dấu đã xử lý | Hiện khi kênh ở trạng thái Error |

Trạng thái: **Active** (đã kết nối & bật) · **Paused** · **Error** · **Disconnected** (chưa kết nối YouTube — bình thường với kênh mới).

## 2. Tạo nhân vật

1. Trong kênh → tab **Nhân vật → + Tạo nhân vật** (hoặc menu **Characters**, chọn kênh sở hữu).
2. Nhập tên, loài, vai trò (chính/phụ — mỗi kênh tối đa 1 nhân vật chính; đặt nhân vật mới làm chính sẽ chuyển nhân vật chính cũ thành phụ).
3. Mô tả **ngoại hình chi tiết và cố định**, phong cách hoạt hình, màu chủ đạo (HEX), trang phục, tính cách, bối cảnh thường xuất hiện, animation được phép.
4. Trong trang nhân vật → **Hình ảnh & biểu cảm**: tải ảnh đại diện, ảnh toàn thân, bộ biểu cảm (đặt tên: `happy`, `sleepy`…), thư viện ảnh tham chiếu (tối đa 30).

### Phiên bản (giữ nhân vật nhất quán)

- Mọi thay đổi ngoại hình hoặc hình ảnh tạo **phiên bản mới**; phiên bản cũ không bao giờ bị sửa.
- Tab **Nhận diện → Tạo phiên bản mới** để đổi trang phục/màu…, kèm ghi chú (VD "Trang phục mùa đông").
- Tab **Phiên bản** → *Dùng phiên bản này* để quay lại phiên bản cũ.
- Đổi tên/loài, lưu trữ không tạo phiên bản.

### Dùng nhân vật ở kênh khác

Mặc định nhân vật chỉ thuộc kênh sở hữu. Tab **Cấp quyền** → chọn kênh nhận + vai trò → *Cấp quyền*. Kênh được cấp chỉ **sử dụng** (đặt vai trò chính/phụ trong kênh mình), không chỉnh sửa. *Thu hồi* bất cứ lúc nào (bị chặn nếu kênh kia đang dùng nhân vật trong nội dung).

## 3. Overview & System Settings

- **Overview**: tổng kênh theo trạng thái, nhân vật, nội dung, video, hàng đợi render/đăng, lượt xem/subscriber/watch time và hoạt động gần đây. Số liệu YouTube hiển thị "—  Chưa đồng bộ" cho tới khi có dữ liệu thật (Phase 4).
- **System Settings**: CPU, RAM, ổ đĩa, kết nối DB, phiên bản migration, FFmpeg, SECRET_KEY, bảo vệ mật khẩu, nhật ký hệ thống.

## 4. Kết nối YouTube, đăng video, lên lịch

Chi tiết (tạo OAuth client, quota, xử lý sự cố): [YOUTUBE_SETUP.md](YOUTUBE_SETUP.md).

1. **Kết nối**: Channels → kênh → tab *YouTube* → *Kết nối YouTube*. Mỗi kênh dùng tài khoản/kênh YouTube riêng.
2. **Lịch đăng của kênh**: Sửa kênh → *Lịch đăng* (múi giờ + các khung giờ trong tuần).
3. **Đăng**: video đã render → *↑ Đăng YouTube*. Mặc định **Private**; có thể hẹn giờ công khai bằng slot trống kế tiếp hoặc giờ cụ thể.
4. **Theo dõi**: *Publishing* (hàng đợi, tiến độ, lịch sử, thử lại/hủy) và *Scheduler* (khung giờ, slot trống, video đã hẹn).

## 5. Các chức năng phase sau

| Hướng dẫn | Phase |
|---|---|
| Xem Analytics, so sánh hiệu suất | 4 |
