# 2. Dataset: tải lên, kiểm tra, xem trước

## 2.1 Hibiscus nhận dataset gì

* Dataset **LeRobot v3.0** (định dạng mặc định của LeRobot 0.7.1 / LeLab). Dataset **v2.1** được
  tự động chuyển đổi sang v3.0.
* Một dataset = một thư mục có `meta/` (`info.json`, `stats.json`, `tasks.parquet`, `episodes/`),
  `data/` và `videos/`. LeLab/`lerobot-record` thường lưu ở
  `~/.cache/huggingface/lerobot/<tên-bạn>/<tên-dataset>`.
* Trên trình duyệt: tải **một file nén** `.zip`, `.tar`, `.tar.gz`, `.tar.zst` hoặc `.rar`
  (RAR5 — kể cả file p7zip không mở được). Tải cả **thư mục**: dùng CLI `hibiscus push` (chương 3).
* Mỗi file nén chỉ chứa **một** dataset.

## 2.2 Tải lên bằng trình duyệt

1. **Dataset › Tải dataset lên**.
2. Kéo thả hoặc **Chọn file**.
3. **Thêm vào**: *Dataset mới* (đặt tên, ví dụ `so101_picknplace`) hoặc *Version mới của dataset có sẵn*.
4. **Tải lên**. Trình duyệt tính dấu vân tay SHA-256 của file trước (file vài GB mất khoảng một
   phút), rồi tải từng phần ≤ 64 MiB.
5. Mất mạng giữa chừng? Việc tải **tự tạm dừng và tự tiếp tục**. Lỡ đóng tab? Mở lại trang Tải
   lên, chọn lại **đúng file đó** → tải tiếp phần còn thiếu.
6. Tải xong là có thể rời trang: máy chủ giải nén và kiểm tra trong nền, bạn nhận thông báo 🔔 khi xong.

## 2.3 Kiểm tra tự động (validation)

Mỗi version qua 7 bước. Trạng thái: *Đang chờ → Đang giải nén → Đang kiểm tra → Sẵn sàng*
(hoặc *Không hợp lệ*, hoặc *Xử lý thất bại* nếu lỗi do máy chủ).

| Bước | Kiểm tra gì |
|---|---|
| Toàn vẹn file | Byte nhận được khớp dấu vân tay tính trên máy bạn |
| Giải nén | Mở an toàn: không có đường dẫn ra ngoài, không symlink, không phải bom nén |
| Cấu trúc thư mục | Có đủ `meta/info.json`, `stats.json`, `tasks.parquet`, `episodes/` |
| Feature và khớp | Kích thước state/action, tên khớp, fps, camera nhất quán |
| Giải mã video | Frame đầu, giữa, cuối của **mọi** episode giải mã được |
| Mốc thời gian | Đều, khớp fps, không thiếu giá trị |
| Thống kê | Tính lại và so với `meta/stats.json` |

* **Lỗi** (đỏ) chặn việc train. Mỗi lỗi ghi rõ episode/file và cách sửa.
* **Cảnh báo** (vàng) không chặn, nhưng hãy đọc: ví dụ *mốc thời gian không đều* (rớt frame khi thu)
  thường giải thích vì sao model kém.
* Sửa xong: tải lên lại thành **version mới** của cùng dataset. Version cũ không bao giờ bị sửa.
* *Xử lý thất bại* (lỗi máy chủ, không phải dữ liệu): bấm **Kiểm tra lại**.

Lỗi hay gặp:

| Thông báo | Thường do | Cách làm |
|---|---|---|
| Không tìm thấy dataset LeRobot trong file nén | Nén nhầm thư mục cha hoặc chỉ nén `videos/` | Nén đúng thư mục chứa `meta/` |
| Không giải mã được một frame video | Dừng thu đột ngột, file video bị cụt | Xóa episode đó bằng công cụ LeRobot (`lerobot-edit-dataset`) hoặc thu lại |
| Dữ liệu có giá trị bị thiếu (NaN) | Đọc motor/cảm biến lỗi khi thu | Xóa/thu lại episode được nêu |
| File nén chứa symbolic link | Nén bằng công cụ giữ link | `tar --dereference -cf ds.tar <thư mục>` |

## 2.4 Xem trước

* **Tổng quan**: định dạng, loại robot, fps, camera, tên khớp, số episode/frame, task, dấu vân tay nội dung.
* **Episode**: lưới ảnh đầu mỗi episode, phân bố độ dài. Mở một episode để xem video và đồ thị
  từng khớp (state = đo được, action = lệnh điều khiển) chạy đồng bộ. Phím ← / → để chuyển episode.
* Video trên web là **bản xem trước chất lượng thấp (H.264)** để trình duyệt nào cũng phát được;
  video gốc (ví dụ AV1) vẫn nguyên và là thứ được dùng để train.

## 2.5 Import từ Hugging Face và gộp dataset

* **Import từ Hugging Face**: nhập `hf://<org>/<repo>` (có thể thêm `@<revision>`). Repo riêng tư
  cần lưu token Hugging Face ở **Tài khoản › Token Hugging Face** trước.
* **Gộp dataset**: chọn nhiều version *Sẵn sàng* có **cùng cấu trúc** (camera, khớp, fps), ví dụ
  nhiều đợt collect → một version mới, được kiểm tra như khi tải lên.

## 2.6 Xóa

Không xóa được dataset/version đang được một lượt train chưa kết thúc dùng. Lượt train và model đã
có vẫn dùng được sau khi xóa dataset.
