# 5. Đọc metrics cho đúng

> **Điều quan trọng nhất**: không con số nào trong Hibiscus là **tỉ lệ thành công trên robot**.
> Loss thấp, sai số offline thấp, huy hiệu "Đã kiểm chứng" — cả ba đều có thể đi cùng một model
> thất bại trên robot thật. Cách duy nhất để biết model tốt là **chạy thử trên robot** (chương 6)
> và đếm số lần thành công.

## 5.1 Loss khi train

* `loss` đo model khớp **dữ liệu train** tốt đến đâu. Nếu train chạy đúng, loss **luôn** giảm.
* Vì vậy loss giảm chỉ chứng tỏ *quá trình train hoạt động*, không chứng tỏ *robot sẽ làm được*.
  Model có thể "học thuộc" các demo và vẫn lúng túng khi vị trí vật thay đổi một chút.
* Ví dụ thật (ACT, dataset mẫu 20 episode, RTX 3060): loss 7,0 ở bước 200 → 2,5 ở bước 600 →
  0,166 ở bước 10 000. Đường cong như vậy là bình thường; nó không nói gì về việc gắp-thả thành công.
* Với ACT, `loss = l1_loss + kl_weight × kld_loss` (mặc định `kl_weight` = 10). `l1_loss` là sai số
  action trên dữ liệu train (đã chuẩn hóa); `kld_loss` là thành phần của VAE, thường về gần 0.
* Đi ngang là bình thường. Nhảy vọt ngắn là bình thường. **Tăng liên tục hoặc thành NaN** là dấu
  hiệu learning rate quá cao hoặc dữ liệu có vấn đề.
* So sánh loss **chỉ có nghĩa giữa các lượt train cùng dataset và cùng policy**. Loss của ACT và
  Diffusion không cùng thang đo.

## 5.2 Các metric khác

| Metric | Đọc thế nào |
|---|---|
| Độ lớn gradient (`grad_norm`) | Nhảy lên rất cao rồi loss thành NaN → giảm learning rate |
| Learning rate (`lr`) | Kiểm tra lịch learning rate đúng như mong muốn |
| Thông lượng (mẫu/giây) | Tốc độ train; giảm mạnh thường do nạp dữ liệu (xem *Thời gian nạp dữ liệu mỗi bước*) |
| Bộ nhớ GPU cao nhất | Gần giới hạn GPU → nguy cơ hết bộ nhớ khi tăng batch |
| GPU (tab GPU) | Mức sử dụng thấp kéo dài → nút thắt ở CPU/nạp video |

## 5.3 Đánh giá offline trên episode giữ lại

* Trước khi train, Hibiscus giữ lại một số episode (mặc định 10 %, ghi trong manifest). Sau khi
  train, model dự đoán action cho từng frame của các episode này và so với action **đã thu**.
* Kết quả: **MAE/MSE** theo từng khớp và trung bình, đơn vị là đơn vị action của dataset (SO-101:
  đơn vị vị trí motor, không phải milimét), cùng đồ thị *dự đoán so với đã thu*.
* Dùng để làm gì: **so sánh** các checkpoint hoặc các lượt train trên **cùng dataset**; phát hiện
  khớp nào học kém (ví dụ gripper).
* Không dùng để làm gì: hứa hẹn robot sẽ thành công. Sai số offline đo việc *bắt chước từng bước
  trên dữ liệu cũ*; trên robot, sai số nhỏ cộng dồn qua hàng trăm bước, vật đặt ở vị trí mới, ánh
  sáng khác… đều có thể làm model thất bại.
* Với 20 episode, giữ lại 10 % chỉ là 2 episode — con số dao động nhiều. Đừng kết luận từ chênh lệch nhỏ.

## 5.4 Huy hiệu "Đã kiểm chứng"

Nghĩa là bundle **đúng kỹ thuật**: (1) LeRobot nạp được và dự đoán ra action hợp lệ,
(2) mọi file khớp `MANIFEST.json`, (3) nếu có ONNX thì kết quả ONNX khớp PyTorch. Nó **không**
nói gì về chất lượng hành vi.

## 5.5 Quy trình khuyên dùng

1. Chạy preset **Nhanh** để chắc dữ liệu và cấu hình ổn.
2. Chạy **Chuẩn**; dùng sai số offline để chọn checkpoint/lượt train tốt nhất *trong số các lựa chọn*.
3. **Thử trên robot**, ví dụ 10 lần với vị trí vật khác nhau; ghi lại tỉ lệ thành công thật.
4. Kém? Thu thêm demo đa dạng hơn (chất lượng và độ đa dạng dữ liệu thường quan trọng hơn tham số),
   tải thành version mới, sao chép lượt train với version mới.
