# 3. CLI `hibiscus` trên máy collect

Máy collect ("máy B") là máy nối với robot, nơi bạn thu dữ liệu bằng LeLab hoặc `lerobot-record`.
CLI `hibiscus` giúp đẩy dataset lên, chạy train và kéo model về mà không cần chép file bằng tay.

> Cú pháp dưới đây theo thiết kế (PLAN §3.7). Kiểm tra lại bằng `hibiscus --help` trên bản CLI
> bạn được cấp; nếu khác, `--help` là đúng.

## 3.1 Cài đặt

CLI là một gói Python (Python ≥ 3.10), **cài riêng**, không cài vào venv của LeLab để tránh
đụng phiên bản thư viện:

CLI **chưa có trên PyPI**: đừng chạy `uv tool install hibiscus` / `pipx install hibiscus` (có
thể cài nhầm một gói khác trùng tên). Cài từ file `.whl` quản trị viên đưa, hoặc từ mã nguồn:

```bash
# từ file wheel (khuyên dùng uv; hoặc pipx install <file>)
uv tool install https://github.com/Bigkatoan/Hibiscus/releases/latest/download/hibiscus-0.1.0-py3-none-any.whl
# hoặc từ mã nguồn
cd Hibiscus/cli && uv tool install .
hibiscus --version
```

Máy có ROS
(biến `PYTHONPATH` trỏ vào `/opt/ros/...`) có thể làm Python chọn nhầm thư viện; khi gặp lỗi lạ,
chạy `env -u PYTHONPATH hibiscus ...`.

## 3.2 Đăng nhập bằng token truy cập (PAT)

1. Trên web: **Tài khoản › Token truy cập › Tạo token**. Đặt tên theo máy (ví dụ
   `may-collect-lab2`), chọn workspace, quyền **Máy collect** (tải dataset lên, chạy train, xem
   log, tải model), hạn 90 ngày.
2. **Sao chép token ngay** — nó chỉ hiện một lần.
3. Trên máy B:

```bash
hibiscus login --server https://robot.example.com
# dán token hbp_... khi được hỏi (không hiện ra màn hình)
```

Hộp thoại tạo token trên web cũng hiện sẵn lệnh này để sao chép. **Đừng** dùng
`hibiscus login --token hbp_...`: token sẽ nằm lại trong lịch sử shell.

Token chỉ làm việc trong **một** workspace. Mất máy hoặc lộ token: thu hồi ngay trên web — máy
đang dùng token sẽ ngừng hoạt động.

## 3.3 Đẩy dataset lên

```bash
# dataset mới
hibiscus push ~/.cache/huggingface/lerobot/<tên-bạn>/so101_picknplace --name so101_picknplace
# version mới của dataset đã có
hibiscus push ~/.cache/huggingface/lerobot/<tên-bạn>/so101_picknplace --dataset so101_picknplace
# hoặc một file nén
hibiscus push ~/Picknplace_20261114_221710.rar --name so101_picknplace
```

* Có thanh tiến độ; mất mạng thì **tự tải tiếp**, chạy lại cùng lệnh cũng tiếp tục từ chỗ dừng.
* Sau khi tải xong, server tự kiểm tra dataset. Mặc định lệnh kết thúc ngay khi tải xong (thoát
  mã 0) và in mã version cùng mã job kiểm tra.
* Thêm `--wait` để CLI đợi kiểm tra xong: in `Validation result: ready` (hoặc `invalid` /
  `failed`) và **thoát với mã 1** nếu dataset Không hợp lệ. Từng bước kiểm tra, số episode lỗi và
  cách sửa xem trên trang dataset trên web hoặc bằng `hibiscus datasets show <tên>`.
* Tự động đẩy sau mỗi đợt thu: `hibiscus watch ~/.cache/huggingface/lerobot/<tên-bạn>`.

## 3.4 Chạy train từ CLI

```bash
hibiscus train --dataset so101_picknplace --policy act --preset standard
hibiscus logs -f 42          # theo dõi lượt train #42 trực tiếp
```

Các bước kiểm tra trước khi chạy giống hệt trên web; nếu bị chặn, CLI in lý do. Muốn chỉnh tham
số chi tiết, dùng trình hướng dẫn trên web (chương 4).

## 3.5 Kéo model về

```bash
hibiscus pull so101_picknplace_act-r42-step100000 --to ~/lelab/models
# chỉ lấy thư mục LeRobot (nhỏ hơn, đủ để chạy robot)
hibiscus pull so101_picknplace_act-r42-step100000 --only pretrained_model --to ~/lelab/models
```

Tải được tiếp nếu đứt mạng; dấu vân tay SHA-256 được kiểm tra sau khi tải. Sau đó xem chương 6
để chạy trên robot.

## 3.6 Lỗi hay gặp của CLI

CLI in thông báo bằng **tiếng Anh**: một dòng `error: …` (mã lỗi của server), thường kèm một dòng
`hint: …` chỉ cách làm. Bảng dưới đây dịch các trường hợp hay gặp:

| CLI in ra (`error:` / `hint:`) | Nghĩa | Cách làm |
|---|---|---|
| `token_revoked` · `this token was revoked: create a new PAT in the web UI and run hibiscus login` | Token đã bị thu hồi | Tạo token mới trên web, chạy lại `hibiscus login` |
| `token_expired` · `this token expired: …` | Token đã hết hạn | Như trên |
| `unauthenticated` · `token missing or invalid: run hibiscus login` / `not logged in to …` | Chưa đăng nhập hoặc token sai | Chạy `hibiscus login --server …` |
| `insufficient_scope` · `the PAT lacks a scope for this command (push: datasets:write, train: runs:write, logs/runs: runs:read, pull: models:read)` | Token thiếu quyền | Tạo token với mẫu quyền **Máy collect** |
| `forbidden` | Không được phép (ví dụ token thuộc workspace khác) | Tạo token cho đúng workspace |
| `quota_exceeded` · `workspace quota reached: ask a workspace admin` | Đã chạm hạn mức | Xóa version/model không dùng hoặc xin admin thêm hạn mức |
| `preflight_failed` | Lượt train sẽ thất bại (bước kiểm tra trước khi chạy) | Đọc các dòng kiểm tra CLI in ra; thử `hibiscus train … --preflight-only` |
| `model_not_ready` | Model còn đang đóng gói | Đợi vài phút rồi chạy lại `hibiscus pull` |
| `dataset_version_not_ready` | Dataset chưa kiểm tra xong | `hibiscus datasets show <tên>` để xem trạng thái |
| `network error: …` | Mất mạng | Chạy lại đúng lệnh cũ: việc tải lên/tải về tự tiếp tục |

Một phần dữ liệu hỏng khi truyền được CLI tự gửi lại, không cần làm gì; nếu lặp lại nhiều lần,
kiểm tra Wi-Fi/cáp.
