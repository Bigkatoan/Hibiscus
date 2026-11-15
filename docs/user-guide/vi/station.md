# Hibiscus Station: ứng dụng chạy cạnh robot

Hibiscus Station chạy trên máy tính cắm robot. Nó thay cho quy trình LeLab: kết nối tay robot,
hiệu chỉnh (calibrate), thêm camera, điều khiển bằng tay leader (teleop), ghi dataset LeRobot, tải
lên workspace Hibiscus, train trên server, kéo model đã train về và chạy trên robot.

Hai điểm Station làm thêm so với LeLab:

* **Sức khỏe động cơ.** Nhiệt độ, điện áp, dòng, tải và cờ báo lỗi của từng động cơ được hiện trên
  mọi màn hình làm robot chuyển động. Động cơ ấm hiện màu vàng (50 °C), nóng màu cam (60 °C: không
  cho bắt đầu phiên mới), nguy hiểm màu đỏ (65 °C hai lần liên tiếp, hoặc cờ quá nhiệt / quá tải).
  Khi nguy hiểm, Station giữ tay robot, đưa về tư thế nghỉ nếu bạn đã lưu, rồi tắt torque, trước khi
  bảo vệ 70 °C của chính servo làm tay robot rơi.
* **Camera khi chạy model.** Màn hình Run model hiện tất cả camera trực tiếp, đúng những khung hình
  model nhận được, bên cạnh vị trí khớp, lệnh điều khiển, nhiệt độ động cơ, tốc độ (FPS) và thời gian
  suy luận. Camera cũng được hiện khi teleop, khi ghi và khi phát lại.

## Cài đặt

Cần có [uv](https://docs.astral.sh/uv/). Sau đó:

Station **chưa có trên PyPI** (đừng cài `hibiscus-station` từ PyPI). Tải file cài từ trang
[Releases](https://github.com/Bigkatoan/Hibiscus/releases) (đã kèm sẵn giao diện):

```bash
uv tool install https://github.com/Bigkatoan/Hibiscus/releases/latest/download/hibiscus_station-0.1.0-py3-none-any.whl
hibiscus-station                  # mở giao diện
```

Hoặc từ mã nguồn: `frontend/scripts/node.sh pnpm build:station && uv tool install ./station`.

Station chạy ở `http://127.0.0.1:18210` và tự mở trình duyệt. Nó chỉ nhận kết nối từ chính máy đó.
Nếu trình duyệt không mở, chạy `hibiscus-station url` và mở đường link được in ra. Muốn thử khi
chưa có robot: `hibiscus-station --mock`.

Hãy tắt LeLab và mọi lệnh `lerobot-*` trước: mỗi cổng serial chỉ một chương trình dùng được.

## Các bước

1. **Robot.** Tạo hồ sơ robot: loại robot, cổng follower, cổng leader (không bắt buộc). "Tìm bằng
   cách rút cáp" và "Tìm bằng cách cử động" giúp chọn đúng cổng. Bấm Connect. Lúc này bạn thấy vị
   trí các khớp và nhiệt độ động cơ. Khi tay robot đang ở tư thế gập an toàn, bấm "Dùng tư thế hiện
   tại làm tư thế nghỉ": Station sẽ đưa tay về đây trước khi tắt torque.
2. **Calibrate.** Với mỗi tay: đưa mọi khớp về giữa hành trình, bấm *Set home*, rồi đưa từng khớp đi
   hết hành trình và bấm *Finish*. File hiệu chỉnh được lưu đúng chỗ lerobot dùng, nên LeLab và các
   lệnh `lerobot-*` dùng lại được. File có sẵn dùng lại được bằng *Dùng hiệu chỉnh này*.
3. **Camera.** Thêm các camera tìm thấy. Tên camera (`wrist`, `front`, ...) là tên model sẽ cần
   (`observation.images.<tên>`).
4. **Teleop.** Cử động tay leader, tay follower làm theo. Nếu leader lệch xa tư thế follower,
   Station yêu cầu bạn đưa leader lại gần trước.
5. **Ghi dữ liệu.** Chọn tên dataset, câu mô tả nhiệm vụ, số episode và độ dài. Phím: **→** sang
   episode tiếp (lưu), **←** ghi lại, **Esc** dừng. Episode chạm giới hạn thời gian sẽ được **lưu**
   (khác LeLab, vốn lặng lẽ ghi lại); bạn có thể đổi thành *bỏ*.
6. **Tải lên.** Ghép Station với server Hibiscus một lần (URL server và personal access token có
   quyền `datasets:write` và `models:read`; thêm `runs:read` để xem các run). Sau đó tải dataset lên
   thành dataset mới hoặc phiên bản mới. Mất mạng giữa chừng thì lần sau tải tiếp từ chỗ dở.
7. **Train.** "Mở trang train trên Hibiscus" mở trang New Run của server. Việc train chạy trên
   server, không bao giờ chạy trên máy robot.
8. **Chạy model.** Nhập file zip bundle hoặc thư mục `pretrained_model`, hoặc kéo model từ server.
   Station kiểm tra model có khớp robot không (số khớp, tên và độ phân giải camera) và đề xuất cách
   sửa. Load model, đặt nhiệm vụ và độ dài episode, rồi bắt đầu.

## An toàn

* **E-stop:** nút đỏ lớn hoặc phím **Space**. Lần bấm đầu: tay robot đứng yên và vẫn giữ torque. Bấm
  lần hai trong vòng 2 giây (hoặc *Relax*): tắt torque, hãy đỡ tay robot. *Đã an toàn, reset* để
  quay lại trạng thái chờ.
* Khi model đang chạy, trình duyệt phải luôn mở: nếu Station không nhận tín hiệu từ trình duyệt
  trong 1 giây, robot sẽ dừng.
* Mỗi bước chuyển động bị giới hạn (`max relative target`, mặc định 5 độ).
* E-stop là phần mềm. Luôn có cách ngắt nguồn robot bằng tay.

## Dữ liệu nằm ở đâu

`~/.hibiscus/station/` chứa hồ sơ robot (`robots.yaml`), cài đặt, dataset (`datasets/<tên>/`, là
dataset LeRobot bình thường; số liệu động cơ nằm cạnh trong `datasets/<tên>.hibiscus/`), model
(`models/`) và nhật ký phiên (`sessions/`). Token server do Hibiscus CLI cất (keyring hệ thống),
không nằm trong thư mục đó.

Trước khi dùng thật, hãy chạy danh sách kiểm tra phần cứng: [station-hardware-uat.md](station-hardware-uat.md).
