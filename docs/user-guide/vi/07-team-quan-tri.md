# 7. Team, token và quản trị

## 7.1 Mời và quản lý thành viên (owner, admin)

* **Thành viên › Mời thành viên**: nhập email, chọn vai trò (Quản trị / Thành viên / Người xem).
* Máy chủ gửi email mời qua **Cloudflare Email Service**. Nếu dịch vụ gửi email chưa bật (Quản
  trị › Hệ thống › Gửi email ghi "Tắt"), Hibiscus hiện **link mời** để bạn tự gửi qua kênh riêng.
  Mọi chức năng vẫn dùng được khi không có email.
* Lời mời có hiệu lực 72 giờ, dùng một lần; **Gửi lại** tạo link mới, link cũ mất hiệu lực.
* Đổi vai trò ngay trong bảng thành viên. Workspace luôn phải còn ít nhất một chủ sở hữu.
* **Gỡ khỏi workspace**: token của người đó cho workspace này bị thu hồi; dữ liệu của họ vẫn ở lại.

## 7.2 Token truy cập cho máy

* Mỗi máy collect một token riêng, đặt tên theo máy, chọn quyền tối thiểu cần thiết:

| Quyền | Cho phép |
|---|---|
| Đọc dataset | Xem/tải dataset |
| Tải dataset lên | Tải dataset lên (gồm quyền đọc) |
| Xem lượt train | Xem lượt train, metrics, log |
| Chạy lượt train | Tạo/điều khiển lượt train (gồm quyền xem) |
| Tải model về | Tải bundle model |

* Preset **Máy collect** = tải dataset lên + chạy lượt train + tải model. Preset **Chỉ đọc** cho máy
  chỉ cần kéo model về.
* Token không hết hạn là có thể nhưng không khuyến nghị. Thu hồi ngay khi mất máy.

## 7.3 Quản trị hệ thống (platform admin)

Khu vực **Quản trị** yêu cầu xác thực hai lớp (và có thể có thêm lớp Cloudflare Access trước đó).

* **Người dùng**: vô hiệu hóa/kích hoạt, mở khóa, cấp/gỡ quyền quản trị hệ thống (người nhận phải
  bật 2FA trước), **đặt lại xác thực hai lớp** (chỉ khi đã xác minh danh tính trực tiếp), đăng xuất
  mọi nơi và thu hồi token, **tạo link đặt lại mật khẩu** (khi không có email; được ghi kiểm toán).
* **Workspace**: tạo workspace mới (bạn là chủ sở hữu).
* **Hạn mức**: mặc định workspace và hạn mức riêng từng người: số lượt chạy cùng lúc, số lượt chờ,
  GPU-giờ/tháng, dung lượng lưu trữ, dung lượng tối đa mỗi lần tải lên.
* **GPU**: *Xả* (chạy nốt lượt hiện tại, không nhận lượt mới — dùng trước khi bảo trì), *Tắt*
  (lượt đang chạy vào lại hàng đợi từ checkpoint gần nhất), *Bật*.
* **Nhật ký kiểm toán**: đăng nhập, thất bại, đổi quyền, tạo/xóa dataset, chạy/hủy lượt train,
  tải model… lọc theo hành động, người dùng, thời gian.
* **Hệ thống**: phiên bản, dung lượng, hàng đợi, tín hiệu worker, nhà cung cấp email.

## 7.4 Thông báo

* Chuông 🔔: lượt train xong/lỗi/treo, model sẵn sàng, dataset sẵn sàng/không hợp lệ.
* **Tài khoản › Kênh thông báo**: thêm Email, Discord, Telegram hoặc webhook; **Gửi tin thử** để
  kiểm tra.
* **Cài đặt workspace › Báo cho mọi thành viên khi**: thông báo chung cho cả nhóm.
