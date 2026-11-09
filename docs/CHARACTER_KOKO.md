# Nhân vật mẫu: Koko — cú mèo kể chuyện đêm khuya

> Giả định ngách: **truyện kể thư giãn / ngủ ngon + nhạc lofi** (video dài 30–60 phút, ít tốn công dựng, dễ lặp lại hàng loạt).
> Nếu bạn làm ngách khác (trẻ em, kiến thức, nấu ăn...), giữ cấu trúc này và đổi phần "Sở thích / Giọng điệu".

## 1. Hồ sơ

| Mục | Nội dung |
|---|---|
| Tên | **Koko** (đọc "Cô-cô"; dễ nhớ, dễ gõ, dùng được cả tiếng Việt và tiếng Anh) |
| Loài | Cú mèo nhỏ, bộ lông kem pha nâu |
| Tuổi "thiết lập" | 7 tuổi cú (khoảng 30 tuổi người), ấm áp, chững chạc |
| Nghề | Thủ thư của "Thư viện lúc nửa đêm" trên một cây sồi cổ |
| Tính cách | Dịu dàng, kiên nhẫn, hơi hay quên, hài hước nhẹ, không bao giờ vội |
| Sở thích | Pha trà hoa cúc, sưu tầm sách cũ, ngắm sao, đan khăn len (đan hoài không xong) |
| Nỗi sợ dễ thương | Tiếng sấm, và việc hết trà |
| Câu cửa miệng | "Chào bạn, đêm nay mình đọc gì nhỉ?" / "Hít một hơi… thở ra. Mình bắt đầu nhé." |
| Lời chào kết | "Ngủ ngon nhé. Koko giữ đèn cho bạn." |

## 2. Đặc điểm nhận dạng (để giữ nhất quán giữa các video)

1. Cặp **kính tròn gọng vàng** hơi lệch xuống mũi.
2. **Khăn len màu mù tạt** quấn cổ, một đầu khăn lúc nào cũng dài hơn.
3. **Một chiếc lông trên đầu dựng lên** như dấu chấm hỏi.
4. Luôn cầm **tách trà nhỏ có hơi nước**.
5. Bảng màu cố định: kem `#F2E3C6`, nâu `#8B5E3C`, mù tạt `#E0A526`, xanh đêm `#1F2A44`, vàng ánh đèn `#FFD98A`.
6. Bối cảnh: thư viện trong thân cây, đèn dầu, cửa sổ nhìn ra trời sao.

## 3. Giọng và phong cách nội dung

- Giọng nữ/trung tính, trầm ấm, nhịp chậm (khoảng 110–125 từ/phút).
- Mở đầu 20 giây: chào + nhắc hít thở. Kết 15 giây: chúc ngủ ngon. Không quảng cáo giữa truyện.
- Mỗi tập là một truyện ngắn, không có cao trào gay gắt, không có cảnh đáng sợ.
- Dòng tập: "Truyện cổ tích đêm khuya", "Chuyện thư viện cây sồi", "Vũ trụ trước giờ ngủ".

## 4. Prompt tạo hình ảnh

Mình không tạo được file ảnh trực tiếp; dùng các prompt này trong Midjourney, DALL·E, Leonardo hoặc Ideogram.

**Ảnh nhân vật chính (đại diện kênh, avatar)**
```
A cozy illustration of Koko, a small cream-and-brown owl librarian, wearing round gold glasses slightly low on her beak,
a mustard-yellow knitted scarf with one longer end, one tuft of feather standing up like a question mark,
holding a tiny steaming teacup. Warm lamplight, soft watercolor and gouache style, gentle rounded shapes,
palette of cream, brown, mustard and deep midnight blue, friendly calm expression, centered, plain dark blue background
```

**Cảnh nền (dùng làm nền video)**
```
Interior of a giant hollow oak tree turned into a library at midnight, wooden shelves full of old books, a glowing oil lamp,
a round window showing a starry sky, a small armchair with a knitted blanket, soft watercolor and gouache style,
warm amber light, deep blue shadows, peaceful, no people, 16:9
```

**Bộ biểu cảm (cần 5 ảnh: vui, buồn ngủ, ngạc nhiên, đang đọc, vẫy tay chào)**
```
Same character as the reference image (Koko the owl, round gold glasses, mustard scarf, question-mark feather tuft),
[expression: sleepy with half-closed eyes / reading an open book / waving hello / surprised / smiling with tea],
same watercolor and gouache style, same palette, plain background
```
Mẹo giữ nhân vật nhất quán: dùng ảnh đầu tiên làm ảnh tham chiếu (Midjourney `--cref`, DALL·E/Leonardo "image guidance"), và luôn lặp lại 5 đặc điểm ở mục 2.

**Thumbnail:** Koko nửa người bên trái, tách trà có hơi nước, nền xanh đêm, chữ lớn ≤ 4 từ (ví dụ "TRUYỆN NGỦ NGON") phông chữ bo tròn màu vàng.

## 5. Gợi ý thiết lập trong Coco Automation

- **Channel:** tên "Koko Kể Chuyện Đêm Khuya", mã kênh 3+ ký tự (vd `koko`), ngôn ngữ vi, mặc định **Private**.
- **Character:** nhập hồ sơ mục 1 và 2, gán ảnh avatar + bộ biểu cảm, chọn giọng đọc.
- **Asset:** tải lên nền thư viện, nhạc lofi/ambient **có bản quyền rõ ràng** (nhạc tự làm hoặc có giấy phép dùng thương mại).

## 6. Việc cần làm để kênh hoạt động

### Giai đoạn 0 — Chốt ý tưởng (1 ngày)
- [ ] Chốt ngách (mặc định: truyện thư giãn) và ngôn ngữ chính
- [ ] Đặt tên kênh và kiểm tra tên chưa bị trùng trên YouTube
- [ ] Chọn lịch đăng đều (đề xuất 3 video/tuần, cùng giờ tối 20:00–21:00)
- [ ] Viết 10 ý tưởng tập đầu tiên

### Giai đoạn 1 — Tài khoản và hạ tầng (1–2 ngày)
- [ ] Tạo Google account riêng cho kênh, bật xác minh 2 bước (làm tay)
- [ ] Tạo kênh YouTube, điền tên, mô tả, banner, avatar (Koko)
- [ ] Xác minh số điện thoại để được tải video dài hơn 15 phút và thumbnail tùy chỉnh
- [ ] Tạo dự án Google Cloud, bật **YouTube Data API v3** và **YouTube Analytics API**
- [ ] Tạo OAuth client (Web), thêm redirect URI `http://localhost:8080/api/youtube/oauth/callback`, thêm tài khoản của bạn vào Test users (xem `docs/YOUTUBE_SETUP.md`)
- [ ] Cài bản Windows (`install-windows.cmd`), `coco start`, đăng nhập dashboard
- [ ] Điền Client ID/Secret vào `.env`, `coco restart`, bấm "Kết nối YouTube" cho kênh

### Giai đoạn 2 — Tài sản (2–4 ngày)
- [ ] Tạo ảnh Koko, bộ biểu cảm, 2–3 cảnh nền (mục 4)
- [ ] Chuẩn bị 5–10 bản nhạc nền **được phép dùng thương mại**, lưu lại nguồn và giấy phép
- [ ] Chọn giọng đọc (tự thu hoặc TTS có giấy phép dùng thương mại), thử đọc 1 đoạn
- [ ] Làm 1 mẫu thumbnail và 1 banner kênh

### Giai đoạn 3 — Sản xuất thử (3–5 ngày)
- [ ] Viết kịch bản tập 1 (khoảng 3.000–4.000 chữ cho video 30 phút)
- [ ] Nhập nhân vật, nội dung, asset vào hệ thống, render 1 video thử
- [ ] Xem lại toàn bộ: âm lượng giọng và nhạc, chữ, hình có bị giật không
- [ ] Đăng chế độ **Private** để kiểm tra upload, tiêu đề, mô tả, thẻ, thumbnail
- [ ] Sửa lỗi, sau đó dựng sẵn 5–8 tập để có "kho" đăng đều

### Giai đoạn 4 — Ra mắt (1 tuần)
- [ ] Đặt lịch đăng 3 tập đầu cùng tuần, chuyển sang Public
- [ ] Khai báo "nội dung do AI tạo/thay đổi" nếu dùng giọng AI hoặc ảnh AI chân thực (theo quy định hiện hành của YouTube)
- [ ] Đặt tên series, danh sách phát (playlist), phần mô tả có mục lục và lời chào Koko
- [ ] Chia sẻ ở vài nhóm/kênh phù hợp (không spam)

### Giai đoạn 5 — Vận hành và cải thiện (liên tục)
- [ ] Mỗi tuần xem trang **Analytics**: thời gian xem, tỷ lệ giữ chân, video mạnh/yếu (dữ liệu đồng bộ từ YouTube, 3 ngày gần nhất chỉ là tạm tính)
- [ ] Mỗi tuần xem trang **Monitoring**: ổ đĩa, RAM, lỗi worker
- [ ] Mỗi tuần `coco backup`; cất bản sao ở ổ khác hoặc đám mây (kèm `.env`)
- [ ] Sau 4 tuần, nhân bản chủ đề video có thời gian xem tốt; bỏ chủ đề yếu
- [ ] Theo dõi điều kiện kiếm tiền YouTube (1.000 người đăng ký và 4.000 giờ xem trong 12 tháng, hoặc điều kiện cập nhật mới nhất trên trang YouTube Partner Program)

## 7. Lưu ý
- Tên và hình Koko do mình sáng tạo; hãy tra nhanh xem có trùng nhân vật/thương hiệu nổi tiếng nào không trước khi đăng ký làm thương hiệu.
- Không dùng nhạc, ảnh, giọng đọc không rõ giấy phép: dễ dính Content ID hoặc bản quyền, làm kênh bị hạn chế kiếm tiền.
- Hệ thống không vượt CAPTCHA/2FA và không né giới hạn quota YouTube; upload mặc định Private, bạn tự duyệt rồi mới công khai.
