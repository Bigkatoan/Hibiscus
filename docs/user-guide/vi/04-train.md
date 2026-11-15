# 4. Train model

## 4.1 Trình hướng dẫn 4 bước

Mở **Tạo lượt train** (hoặc **Train với version này** trên trang dataset).

1. **Dataset**: chọn dataset và version (chỉ version *Sẵn sàng*). **Episode giữ lại để đánh giá**:
   mặc định 10 % (với 20 episode là 2 episode). Các episode này không dùng để train mà để đo sai số
   offline sau đó (chương 5). Đặt 0 % thì không có đánh giá offline.
2. **Policy**: chọn kiến trúc. Thẻ bị mờ kèm lý do khi dataset không đáp ứng (ví dụ TD-MPC cần
   reward). Lần đầu hãy chọn **ACT**.
3. **Tham số**: chọn **preset** rồi chỉnh nếu cần. Tab *Cơ bản* có các tham số quan trọng, mỗi
   trường có giải thích và giá trị mặc định; tab *Nâng cao* là mọi tham số khác của
   `lerobot-train` (LeRobot 0.7.1), kèm tên cờ LeRobot.
4. **Xem lại và chạy**: các tham số đã đổi, GPU (*Tự động* là lựa chọn tốt), tùy chọn đóng gói
   (ONNX, đánh giá offline), **ước tính** bộ nhớ GPU và thời gian, và **kiểm tra trước khi chạy**.
   Bấm **Bắt đầu train**.

Muốn chạy lại với thay đổi nhỏ: mở lượt train cũ › **Sao chép cấu hình sang lượt mới**.

## 4.2 Chọn policy

| Policy | Khi nào dùng | GPU | ONNX |
|---|---|---|---|
| **ACT** | Lựa chọn đầu tiên; vài chục demo là chạy tốt; train nhanh | RTX 3060 và P40 | Có |
| Diffusion Policy | Demo đa dạng (nhiều cách làm cùng một việc) | cả hai | Có (encoder + denoiser) |
| VQ-BeT | Hành vi đa dạng, rời rạc hóa action | cả hai | Có thể có ở v1.1 |
| TD-MPC | Cần dataset có reward (`next.reward`) | cả hai | Không |
| SmolVLA (~450M) | Làm theo mô tả task bằng chữ; cần nhiều VRAM | 3060 hạn chế (bf16, batch nhỏ), P40 tốt | Không |
| Pi0 / Pi0.5 (~3B) | Thử nghiệm; chỉ tinh chỉnh LoRA | Chỉ P40 | Không |

## 4.3 Preset

| Preset | Bước | Dùng để | ACT trên RTX 3060 (đã đo, batch 8) |
|---|---|---|---|
| Nhanh | 10 000 | Kiểm tra dữ liệu và cấu hình chạy được | khoảng 20 phút |
| Chuẩn | 100 000 | Model thật | khoảng 3 giờ |
| Tinh chỉnh | 20 000 | Train tiếp từ model có sẵn / checkpoint Hub | tùy model |

Số đo trên là của dataset mẫu (20 episode, 1 camera 640×360) trên RTX 3060: ~0,11 giây/bước,
~1,8 GB VRAM. Dataset khác sẽ khác; trang Xem lại cho ước tính riêng (nguồn ước tính được ghi rõ:
*đo bằng chạy thử 20 bước*, *dựa trên lần đo trước*, hoặc *ước tính thô*).

## 4.4 Tham số hay chỉnh

* **Batch size**: số mẫu mỗi bước. Lỗi hết bộ nhớ → giảm một nửa.
* **Số bước train**: loss thường đi ngang trước khi hết; nhiều bước hơn chưa chắc tốt hơn trên robot.
* **Lưu checkpoint mỗi N bước**: tạm dừng/chạy tiếp và đóng gói model đều dựa trên checkpoint.
* **Mixed precision**: `bf16` nhanh và tiết kiệm bộ nhớ trên RTX 3060. **Tesla P40 không hỗ trợ**:
  lượt train trên P40 luôn chạy fp32 (bạn sẽ thấy cảnh báo, không phải lỗi).
* **Tăng cường ảnh**: bật khi ánh sáng lúc chạy robot khác lúc thu.
* ACT: **Kích thước chunk action** và **Số action thực thi mỗi lần dự đoán** (không được lớn hơn chunk).

## 4.5 Hàng đợi và GPU

* Lượt train vào **hàng đợi**; thứ tự theo độ ưu tiên rồi **fair-share** giữa các thành viên.
  Xem **Hàng đợi GPU** để biết vị trí và GPU nào đang bận.
* Mỗi người mặc định chạy **1 lượt cùng lúc**; lượt thứ hai sẽ chờ.
* GPU: `cuda0` = RTX 3060 12 GB (bf16), `cuda1` = Tesla P40 24 GB (fp32, chậm hơn nhưng nhiều bộ nhớ).

## 4.6 Trong lúc train

Trang lượt train cập nhật trực tiếp: trạng thái, bước/tổng, thời gian còn lại, checkpoint kế
tiếp, metrics, log, GPU.

| Trạng thái | Nghĩa |
|---|---|
| Đang chờ | Chờ GPU rảnh |
| Đang chuẩn bị | Đã có GPU; tải dataset, khởi động LeRobot |
| Đang train | Đang chạy `lerobot-train` |
| Đang tạm dừng / Đã tạm dừng | Xem 4.7 |
| Đang đóng gói model | Train xong; đang tạo bundle, đánh giá offline, xuất ONNX, kiểm chứng |
| Thành công / Thất bại / Đã hủy | Kết thúc |

Cảnh báo (khung vàng) cần để ý: *loss thành NaN*, *không có output 5 phút* (có thể treo; tự dừng
sau 15 phút), *bộ nhớ GPU trên 95 %*, *tự chạy lại sau sự cố máy chủ*.

## 4.7 Tạm dừng, chạy tiếp, hủy

* **Tạm dừng › Ở checkpoint kế tiếp** (khuyên dùng): train tiếp tới checkpoint sau (trang ghi bước
  và thời gian), lưu, rồi trả GPU. Không mất tiến độ.
* **Tạm dừng › Ngay lập tức**: dừng ngay, mất phần từ checkpoint gần nhất. Nếu chưa có checkpoint,
  chạy tiếp sẽ bắt đầu lại từ bước 0 (cùng seed).
* **Chạy tiếp**: vào lại hàng đợi, train tiếp từ checkpoint gần nhất, có thể trên GPU khác.
* **Hủy**: dừng hẳn; các checkpoint đã lưu vẫn đóng gói thành model được.
* Lỗi máy chủ (mất worker, lỗi GPU…) được **tự chạy lại một lần** từ checkpoint gần nhất.

## 4.8 Khi lượt train thất bại

Trang hiển thị **Vì sao lượt train thất bại** và các dòng log cuối, kèm nút gợi ý:

| Lý do | Nên làm |
|---|---|
| GPU hết bộ nhớ | **Sao chép với batch size giảm một nửa**, hoặc chọn Tesla P40 |
| Loss liên tục thành NaN | **Sao chép với learning rate thấp hơn**; kiểm tra dataset có NaN |
| LeRobot từ chối cấu hình | Đọc log để biết tham số; **Sao chép và sửa cấu hình** |
| Worker mất kết nối / lỗi GPU / treo | **Chạy tiếp** từ checkpoint |
| Hết GPU-giờ trong tháng | Lượt train tự tạm dừng; chạy tiếp khi có hạn mức |

## 4.9 Sau khi xong

* Tab **Checkpoint**: đóng gói model từ bất kỳ checkpoint nào, hoặc đánh giá offline từng checkpoint.
* **So sánh lượt train**: chọn 2–8 lượt trong danh sách › **So sánh các lượt đã chọn**.
* **Manifest tái lập** (tab Cấu hình): version LeRobot/torch/CUDA, image, dấu vân tay dataset,
  cấu hình đầy đủ và seed — đủ để chạy lại y hệt.
