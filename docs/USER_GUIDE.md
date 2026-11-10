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

- **Overview**: tổng kênh theo trạng thái, nhân vật, nội dung, video, hàng đợi render/đăng, lượt xem/subscriber/watch time và hoạt động gần đây. Số liệu YouTube hiển thị "—  Chưa đồng bộ" cho tới khi có dữ liệu thật (xem mục 5).
- **System Settings**: CPU, RAM, ổ đĩa, kết nối DB, phiên bản migration, FFmpeg, SECRET_KEY, bảo vệ mật khẩu, nhật ký hệ thống.

## 4. Kết nối YouTube, đăng video, lên lịch

Chi tiết (tạo OAuth client, quota, xử lý sự cố): [YOUTUBE_SETUP.md](YOUTUBE_SETUP.md).

1. **Kết nối**: Channels → kênh → tab *YouTube* → *Kết nối YouTube*. Mỗi kênh dùng tài khoản/kênh YouTube riêng.
2. **Lịch đăng của kênh**: Sửa kênh → *Lịch đăng* (múi giờ + các khung giờ trong tuần).
3. **Đăng**: video đã render → *↑ Đăng YouTube*. Mặc định **Private**; có thể hẹn giờ công khai bằng slot trống kế tiếp hoặc giờ cụ thể.
4. **Theo dõi**: *Publishing* (hàng đợi, tiến độ, lịch sử, thử lại/hủy) và *Scheduler* (khung giờ, slot trống, video đã hẹn).

## 5. Xem Analytics (Phase 4)

Menu **Analytics** (toàn hệ thống) hoặc tab **Analytics** trong trang một kênh.

**Đồng bộ dữ liệu.** Worker `analytics` tự đồng bộ mỗi kênh đã kết nối mỗi 6 giờ (`ANALYTICS_SYNC_INTERVAL_MINUTES`).
Bấm **⟳ Đồng bộ ngay** để đồng bộ tức thì (lần đầu lấy 90 ngày gần nhất). Thanh đồng bộ cho biết kênh nào *Đã đồng bộ / Chưa đồng bộ / Lỗi*
và lý do (thiếu quyền Analytics, token bị thu hồi, hết quota…). Một kênh lỗi không ảnh hưởng kênh khác.

**Phân biệt nguồn số liệu** (mỗi số đều có nhãn):

| Nhãn | Ý nghĩa |
|---|---|
| **YouTube API** | Số liệu thực YouTube trả về, lưu nguyên văn |
| **Sơ bộ** | 3 ngày gần nhất — YouTube còn điều chỉnh (vùng vàng trên biểu đồ) |
| **Coco tính toán** | Điểm hiệu quả, % tăng trưởng, đề xuất — Coco tính từ số liệu YouTube |
| **Chưa đồng bộ** | Hiển thị “—”. Ngày YouTube không trả dữ liệu **không** bị vẽ thành 0 |

**Bộ lọc:** kênh, từ ngày – đến ngày, chủ đề (loại nội dung), trạng thái video (public/unlisted/private). Khi lọc theo chủ đề/trạng thái,
số liệu được cộng từ báo cáo từng video (không có “subscriber mất”).

**Tab Biểu đồ:** đường lượt xem/watch time/subscriber/likes/comments theo ngày-tuần-tháng (có thể tách theo kênh);
cột so sánh video; donut phân bổ lượt xem; so sánh kênh (tăng trưởng so với kỳ liền trước, “Tốt nhất” = nhiều watch time nhất);
đường giữ chân người xem trung bình.

**Tab Hiệu suất video:** bảng từng video (lượt xem, watch time, thời gian xem TB, % xem, giữ chân, sub mới, tương tác). Bấm số *Giữ chân* để xem đường
giữ chân và đoạn rơi mạnh nhất. Cột **Đánh giá** chấm điểm 0–100 *trong cùng kênh* (không so video kênh này với kênh khác) bằng percentile của:
watch time/ngày (30%), % xem TB (20%), giữ chân (15%), subscriber/1000 lượt xem (15%), tương tác (10%), lượt xem/ngày (10%) —
**không chỉ lượt xem**. Cần ≥ 4 video đã đăng ≥ 3 ngày trong kênh; video thấp điểm có nút *Vì sao thấp?* nêu số liệu cụ thể.

**Tab Đánh giá & đề xuất:** hiệu quả theo chủ đề, thời lượng (30 phút–8 giờ), khung giờ & ngày đăng (theo múi giờ của kênh, đo bằng lượt xem 7 ngày đầu,
chỉ video đủ 8 ngày dữ liệu; cột nhạt = dưới 3 mẫu), video yếu và danh sách **đề xuất nội dung tiếp theo** kèm số liệu căn cứ và độ tin cậy.
Khi chưa đủ dữ liệu, hệ thống nói rõ thay vì đoán. Đề xuất chủ đề chỉ là hướng đi — hãy tạo nội dung **mới** (bối cảnh/âm thanh khác), không nhân bản hàng loạt chỉ đổi tiêu đề.

## 6. Monitoring (Phase 5)

Menu **Monitoring** cho biết hệ thống có khỏe không: banner *OK / cảnh báo / nghiêm trọng* kèm cách xử lý, CPU/RAM/ổ đĩa, database,
lịch sử tài nguyên, 4 worker (render, upload, analytics, monitor), hàng đợi, tiến trình FFmpeg và sức khỏe YouTube.
- **Kiểm tra tác vụ treo**: chạy watchdog ngay (tác vụ không còn tiến triển được khôi phục tự động).
- **Dọn dẹp ngay**: xóa nhật ký/số đo/file tạm cũ.

Khi có cảnh báo, trang Overview hiện dải thông báo dẫn tới Monitoring. Toàn bộ cơ chế khôi phục: [OPERATIONS.md](OPERATIONS.md).

## 7. Backup & restore

Xem [BACKUP_RESTORE.md](BACKUP_RESTORE.md).

## 8. Cảnh 3D (xem tương tác & render ra video)

Mở một dự án nội dung → tab **Cảnh 3D**.

1. **Dàn dựng**: chọn bối cảnh (phòng học, cửa sổ mưa, nhà gỗ, quán cà phê), thời điểm, mưa/gió/sương mù, lò sưởi, đèn.
   Kéo chuột để xoay, cuộn để zoom; bấm vào cửa sổ / lò sưởi / đèn / nhân vật để tương tác. Bấm *Dùng góc nhìn hiện tại làm camera* rồi **Lưu cảnh 3D**.
2. **Nhân vật**: mặc định là nhân vật tạm. Tải model `.glb` của bạn ở mục **Assets** (khai báo giấy phép như mọi tài nguyên) rồi chọn ở đây; gán animation cho "đứng yên" và các phản ứng (bấm vào, mưa lớn, lửa tắt, giờ nghỉ).
3. **Render**: khi dự án có cảnh 3D, cảnh **thay thế** hình nền 2D / animation 2D / ảnh nhân vật 2D. Tab *Render* vẫn dùng âm thanh, đồng hồ Pomodoro, hàng đợi, kiểm tra chất lượng và thumbnail như cũ.
   Hệ thống chụp một **vòng lặp liền mạch** (mặc định 20 giây, 15 khung/giây rồi nhân đôi lên 30 fps) bằng Chromium không giao diện, sau đó FFmpeg lặp lại đến 30 phút – 8 giờ. Không cần GPU; xem trước 10–60 giây để kiểm tra trước khi render dài.

Cấu hình trong `.env` (tùy chọn): `CHROMIUM_PATH`, `SCENE3D_FPS` (mặc định 15), `SCENE3D_LOOP_SECONDS` (mặc định 20), `SCENE3D_SOFTWARE_GL` (mặc định true).
Lưu ý: nhân vật 2D của Character Manager không dùng trong cảnh 3D; dùng model `.glb` thay thế.
