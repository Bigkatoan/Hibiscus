# 8. Xử lý sự cố

Mọi thông báo lỗi trong Hibiscus có tiêu đề, giải thích và việc cần làm. Danh sách đầy đủ (tiếng
Việt và tiếng Anh) ở `docs/ux/error-catalogue.md`. Khi báo lỗi cho quản trị viên, gửi kèm **Mã
yêu cầu** (nút Sao chép cạnh thông báo) và số lượt train (ví dụ `#42`).

| Tình huống | Làm gì |
|---|---|
| "Phiên đăng nhập đã kết thúc" | Đăng nhập lại; dữ liệu đang nhập trong trình hướng dẫn được giữ |
| "Kiểm tra bảo mật thất bại" ở trang đăng nhập | Tải lại trang; tắt VPN/trình chặn quảng cáo nếu lặp lại |
| "Mã bảo mật của trang đã cũ" | Tải lại trang (thường do đăng nhập ở tab khác) |
| "Không tìm thấy" một trang/dataset | Có thể bị xóa, hoặc thuộc workspace bạn không phải thành viên |
| Biểu đồ đứng yên, chỉ báo "Mất kết nối, đang kết nối lại…" | Đợi vài giây; vẫn vậy thì tải lại trang. Việc train **không** bị ảnh hưởng |
| Tải lên dừng giữa chừng | Mở lại trang Tải lên, chọn lại đúng file để tải tiếp; CLI: chạy lại cùng lệnh |
| "File quá lớn" / "Đã chạm hạn mức" | Chia dataset rồi gộp sau, xóa dữ liệu cũ, hoặc xin admin thêm hạn mức |
| Dataset "Không hợp lệ" | Mở tab Kiểm tra; mỗi lỗi ghi episode và cách sửa (chương 2.3) |
| Lượt train chờ lâu | Xem Hàng đợi GPU: có thể cả hai GPU đang bận, hoặc bạn đã có 1 lượt đang chạy |
| "Không đủ bộ nhớ GPU" trước khi chạy | Giảm batch size, bật gradient checkpointing/LoRA, hoặc chọn Tesla P40 |
| Lượt train thất bại | Đọc "Vì sao lượt train thất bại" và bấm nút gợi ý (chương 4.8) |
| Model "Chưa kiểm chứng" vì ONNX không đạt | Không dùng `onnx/`; `pretrained_model/` vẫn dùng bình thường với LeRobot |
| Robot không chạy | Chương 6.6 |
| Model kiểm chứng đạt, sai số offline thấp nhưng robot làm hỏng | Bình thường có thể xảy ra (chương 5): thu thêm demo đa dạng, thử checkpoint khác, kiểm tra camera/ánh sáng giống lúc thu |
