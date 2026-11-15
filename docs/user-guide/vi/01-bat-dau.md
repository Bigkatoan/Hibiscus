# 1. Bắt đầu: tài khoản, bảo mật, workspace

## 1.1 Dùng ngay trên trình duyệt, không cần cài đặt

Mở **https://robot.example.com** bằng Chrome, Firefox, Edge hoặc Safari bản mới, trên máy tính
hay điện thoại. Toàn bộ việc tải dataset, train, xem metrics và tải model đều làm được trên web.
Chỉ máy collect (máy nối robot) mới cần thêm CLI `hibiscus` (chương 3) — và kể cả máy đó cũng
có thể dùng trình duyệt thay cho CLI.

Ngôn ngữ: chọn **Tiếng Việt / English** ở góc trên. Lựa chọn được lưu theo tài khoản.

## 1.2 Tài khoản chỉ có qua lời mời

Hibiscus mở ra Internet nên không có trang đăng ký công khai.

1. Owner hoặc admin của workspace gửi lời mời tới email của bạn. Nếu máy chủ chưa bật gửi email,
   họ sẽ gửi cho bạn một **link mời** qua kênh riêng (Zalo, Slack…).
2. Mở link (có hiệu lực **72 giờ**, dùng **một lần**) → nhập tên, mật khẩu (tối thiểu
   **12 ký tự**; mật khẩu nằm trong danh sách bị lộ sẽ bị từ chối) → **Tạo tài khoản và tham gia**.
3. Nếu bạn đã có tài khoản: đăng nhập trước rồi mở link → **Chấp nhận lời mời**.

Link báo "đã hết hạn" hoặc "không dùng được"? Nhờ người mời bấm **Gửi lại** — link cũ sẽ mất hiệu lực.

## 1.3 Đăng nhập và xác thực hai lớp

* Đăng nhập bằng email + mật khẩu. Có thể có ô "Kiểm tra bảo mật" (Cloudflare Turnstile) để chặn bot.
* Sai mật khẩu nhiều lần liên tiếp, tài khoản bị **khóa tạm thời**; đợi rồi thử lại, hoặc đặt lại mật khẩu.
* **Xác thực hai lớp** (ứng dụng Aegis, Google Authenticator, 1Password…):
  * **Bắt buộc** với Chủ sở hữu, Quản trị và Quản trị hệ thống — hệ thống sẽ dẫn bạn cài ngay.
  * Khuyến nghị cho mọi người: **Tài khoản › Bảo mật › Cài đặt xác thực hai lớp**.
  * Khi bật, bạn nhận **10 mã khôi phục**. Cất ở nơi an toàn, ngoài máy dùng chung. Mỗi mã dùng
    được một lần, dùng khi mất điện thoại. Sắp hết thì bấm **Tạo bộ mã khôi phục mới**.
* Mã 6 số luôn sai? Kiểm tra đồng hồ điện thoại có tự đồng bộ giờ không.

## 1.4 Quên mật khẩu

**Quên mật khẩu?** → nhập email → nhận link đặt lại (dùng một lần, hiệu lực ngắn). Đặt mật khẩu
mới sẽ **đăng xuất mọi thiết bị**. Nếu trang báo máy chủ chưa gửi được email, nhờ quản trị viên tạo
link đặt lại cho bạn (Quản trị › Người dùng › Tạo link đặt lại mật khẩu).

## 1.5 Workspace và vai trò

Dữ liệu (dataset, lượt train, model) thuộc về **workspace** (nhóm), không thuộc cá nhân. Đổi
workspace ở menu trên cùng bên trái.

| Vai trò | Làm được |
|---|---|
| Chủ sở hữu (owner) | Mọi thứ, kể cả xóa workspace. Bắt buộc 2FA |
| Quản trị (admin) | Mời/gỡ thành viên, đổi vai trò, điều khiển mọi lượt train, đặt độ ưu tiên cao. Bắt buộc 2FA |
| Thành viên (member) | Tải dataset, chạy và điều khiển lượt train **của mình**, tải model |
| Người xem (viewer) | Chỉ xem |

Hai GPU dùng chung cho mọi người theo nguyên tắc **fair-share**: ai dùng ít GPU gần đây hơn được
chạy trước. Hạn mức mặc định: **1 lượt train chạy cùng lúc mỗi người**, 200 GPU-giờ/tháng,
200 GiB lưu trữ mỗi workspace, tối đa 50 GiB mỗi lần tải lên. Xem **Mức sử dụng** để biết bạn còn bao nhiêu.

## 1.6 Phiên đăng nhập và an toàn

* **Tài khoản › Bảo mật › Phiên đăng nhập**: xem các thiết bị đang đăng nhập, đăng xuất từ xa.
* Nếu thấy thông báo "Đã đăng xuất để bảo vệ tài khoản": phiên của bạn bị dùng ở hai nơi cùng lúc.
  Hãy đăng nhập lại và đổi mật khẩu.
* Không chia sẻ tài khoản. Máy collect dùng **token truy cập** riêng (chương 3), không dùng mật khẩu của bạn.
