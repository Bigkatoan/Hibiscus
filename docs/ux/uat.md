# Kịch bản nghiệm thu (UAT) — Hibiscus v1

> Người chạy: chủ lab (bạn). Thời lượng: khoảng 3–4 giờ (phần lớn là chờ train). Chạy trên hệ
> thống thật qua `https://robot.example.com` sau khi Phase 3 tích hợp xong (PLAN §8.3 Phase 6).
> Mỗi bước: làm đúng cột **Thao tác**, so với cột **Kết quả mong đợi**, đánh dấu Đạt/Không đạt và
> ghi chú (ảnh chụp màn hình nếu không đạt). Một bước "Không đạt" ở mục có dấu ★ là **chặn nghiệm thu**.
>
> English summary: step-by-step acceptance test for the lab owner; ★ = release-blocking.
> Each row: action → expected result → pass/fail.

## 0. Chuẩn bị

| Hạng mục | Cần có |
|---|---|
| Máy chủ | Máy GPU (RTX 3060 = `cuda0`, Tesla P40 = `cuda1`), Hibiscus chạy bằng `docker compose`, tunnel Cloudflare trỏ về `http://localhost:18000` |
| Email | Cloudflare Email Service đã cấu hình (provider `cloudflare`). Nếu chưa xác minh được, chạy các bước có ký hiệu ✉ theo nhánh "không có email" |
| Tài khoản | 3 địa chỉ email: **A** (bạn, quản trị), **B** (thành viên), **C** (người xem) |
| Điện thoại | Ứng dụng xác thực (Aegis / Google Authenticator / 1Password) |
| Máy collect ("máy B") | Linux có venv LeLab `~/lelab/leLab/.venv`, cài CLI `hibiscus`, nối tay SO-101 follower + camera cổ tay |
| Dữ liệu | `~/lelab/Picknplace_20261114_221710.rar` (RAR5) và thư mục dataset `so101_picknplace_20261114` (LeRobot v3.0, 20 episode, camera `wrist_cam` AV1 640×360) |
| Trình duyệt | Firefox hoặc Chrome bản mới; một cửa sổ ẩn danh cho tài khoản B/C |

Ghi kết quả vào bảng ở cuối file (hoặc bản sao của file này).

---

## 1. Khởi tạo và bảo mật tài khoản

| ID | Thao tác | Kết quả mong đợi | Đạt? |
|---|---|---|---|
| UAT-01 ★ | Trên máy chủ chạy lệnh bootstrap (runbook): `python -m app.admin.bootstrap --email <A>`. Mở link in ra | Trang "Tạo tài khoản", email A bị khóa không sửa được | |
| UAT-02 ★ | Đặt mật khẩu `password1234` | Bị từ chối: "Mật khẩu đã bị lộ" (hoặc "quá yếu"), có hướng dẫn chọn mật khẩu khác | |
| UAT-03 ★ | Đặt mật khẩu mạnh ≥ 12 ký tự, tên "Khoa" | Tài khoản được tạo, **bắt buộc** chuyển sang cài xác thực hai lớp, không có nút "để sau" | |
| UAT-04 ★ | Quét QR bằng điện thoại, nhập mã | Hiện 10 mã khôi phục; nút Tiếp tục chỉ bật sau khi tích "Tôi đã cất giữ mã khôi phục". Tải .txt được | |
| UAT-05 | Quản trị › Workspace › Tạo workspace "Lab SO-101", slug `lab-so101` | Workspace được tạo, bạn là Chủ sở hữu | |
| UAT-06 ★ | Đăng xuất, đăng nhập lại bằng A + mã 6 số | Vào được; nhập sai mã → "Sai mã…" và vẫn ở bước nhập mã | |
| UAT-07 | Đăng xuất, đăng nhập bằng một **mã khôi phục** | Vào được; Bảo mật › Mã khôi phục hiện "Còn 9 mã chưa dùng" | |
| UAT-08 | Nhập sai mật khẩu 6 lần liên tiếp cho A | Từ lần thứ 6: "Tài khoản tạm thời bị khóa", có thời gian chờ; đúng mật khẩu sau thời gian chờ thì vào được | |
| UAT-09 | Đổi ngôn ngữ sang English rồi về Tiếng Việt (menu ngôn ngữ) | Toàn bộ giao diện đổi ngay, không còn chữ tiếng Anh sót ở trang đang mở; lựa chọn được giữ sau khi tải lại trang | |

## 2. Team và phân quyền

| ID | Thao tác | Kết quả mong đợi | Đạt? |
|---|---|---|---|
| UAT-10 ★ ✉ | Thành viên › Mời thành viên: email B, vai trò Thành viên | **Có email**: thông báo "Đã gửi lời mời…", B nhận email trong vài phút (kiểm tra cả spam). **Không có email**: hộp thoại "Chia sẻ link mời này" có nút Sao chép | |
| UAT-11 ★ | Ở cửa sổ ẩn danh, mở link mời của B, tạo tài khoản | Biểu ngữ "Khoa mời bạn vào Lab SO-101 với vai trò Thành viên"; tạo xong vào thẳng workspace; B **không** bị bắt cài 2FA | |
| UAT-12 | Mở lại đúng link mời đó lần nữa | "Link mời này không dùng được" | |
| UAT-13 | Mời C với vai trò Người xem, C chấp nhận | C thấy dataset/lượt train/model nhưng không có nút Tải lên, Tạo lượt train, Hủy, Xóa | |
| UAT-14 ★ | Với tài khoản C, mở trực tiếp URL `/w/lab-so101/runs/new` | Trang "Bạn không có quyền truy cập", không lộ dữ liệu | |
| UAT-15 ★ | A tạo thêm workspace "Riêng" (không mời B). Với B, mở URL một dataset của workspace "Riêng" (copy từ A) | B thấy "Không tìm thấy trang" (không phải "không có quyền") | |
| UAT-16 | A đổi B thành Quản trị | Lần thao tác tiếp theo B bị yêu cầu cài xác thực hai lớp trước khi tiếp tục | |
| UAT-17 ✉ | Đăng xuất B, bấm "Quên mật khẩu?" với email B | **Có email**: thông báo trung tính "Nếu có tài khoản…", nhận email, đặt lại thành công, mọi phiên khác bị đăng xuất. **Không có email**: hiện hướng dẫn nhờ quản trị viên; A vào Quản trị › Người dùng › Tạo link đặt lại mật khẩu, gửi cho B, B đặt lại được | |
| UAT-18 | Quản trị › Nhật ký kiểm toán | Có các dòng: đăng nhập, đăng nhập thất bại, khóa tài khoản, tạo lời mời, chấp nhận lời mời, đổi vai trò, (tạo link đặt lại) — tiếng Việt, đúng người, đúng giờ | |
| UAT-19 | Quản trị › Hệ thống | Hiện phiên bản Hibiscus/LeRobot 0.7.1, hai worker có tín hiệu gần đây, "Gửi email: Cloudflare Email Service" (hoặc "Tắt — …") | |

## 3. Máy collect: token và CLI

| ID | Thao tác | Kết quả mong đợi | Đạt? |
|---|---|---|---|
| UAT-20 ★ | A: Tài khoản › Token truy cập › Tạo token "may-collect-lab", preset "Máy collect", 90 ngày | Token `hbp_…` hiện **một lần**, có nút Sao chép và gợi ý lệnh `hibiscus login --server …`; không đóng được hộp thoại trước khi tích "Tôi đã sao chép token" | |
| UAT-21 ★ | Máy B: `hibiscus login --server https://robot.example.com`, dán token | CLI in tên bạn, workspace Lab SO-101, các quyền | |
| UAT-22 | Tải lại trang Token truy cập | Token hiện "Dùng lần cuối … từ <IP máy B>"; không bao giờ hiện lại chuỗi token | |

## 4. Dataset

| ID | Thao tác | Kết quả mong đợi | Đạt? |
|---|---|---|---|
| UAT-23 ★ | Trình duyệt (A): Dataset › Tải dataset lên › chọn `Picknplace_20261114_221710.rar`, Dataset mới tên `so101_picknplace` › Tải lên | Thanh "Đang kiểm tra toàn vẹn file…" rồi "Đang tải phần n/N" có tốc độ và thời gian còn lại | |
| UAT-24 ★ | Khi đang tải khoảng 30 %, tắt Wi-Fi/rút mạng 1 phút rồi bật lại | Hiện "Mất kết nối… sẽ tự tiếp tục"; khi có mạng thì tải tiếp từ phần đang dở, không bắt đầu lại từ 0 | |
| UAT-25 | Tải lần 2 cùng file: bắt đầu rồi đóng tab ở khoảng 50 %, mở lại trang Tải lên | Biểu ngữ "Có một lượt tải … chưa xong"; chọn lại đúng file → tải tiếp phần còn thiếu. Chọn file khác → báo "Đây không phải file của lượt tải dở". (Xong thì Hủy tải lên lượt này) | |
| UAT-26 ★ | Đợi lượt tải ở UAT-23 xong | "Đã tải xong… bạn có thể rời trang này"; trạng thái version đổi trực tiếp Đang giải nén → Đang kiểm tra → Sẵn sàng (hoặc "Đạt, có cảnh báo") mà không cần tải lại trang; có thông báo 🔔 | |
| UAT-27 ★ | Mở tab Kiểm tra | 7 bước (Toàn vẹn file, Giải nén, Cấu trúc thư mục, Feature và khớp, Giải mã video, Mốc thời gian, Thống kê), mỗi bước có biểu tượng + chữ; cảnh báo (nếu có) ghi rõ episode và cách xử lý | |
| UAT-28 | Tab Tổng quan | 20 episode, 30 fps, camera `observation.images.wrist_cam`, 6 khớp `shoulder_pan.pos … gripper.pos`, định dạng v3.0 | |
| UAT-29 | Tab Episode › mở episode 0, bấm phát | Video (bản xem trước) phát được trong trình duyệt; đồ thị 6 khớp state/action, vạch con trỏ chạy theo video; phím ←/→ chuyển episode | |
| UAT-30 ★ | Máy B: `hibiscus push <thư mục so101_picknplace_20261114> --dataset so101_picknplace` | CLI tải lên có thanh tiến độ, in các bước kiểm tra; trên web dataset có **v2**. Nếu nội dung y hệt v1 thì báo "Dữ liệu đã được tải lên" — chấp nhận được | |
| UAT-31 | Thử tải một file `.7z` hoặc `.pdf` | Bị từ chối ngay trên trình duyệt: "Định dạng nén không được hỗ trợ…" | |
| UAT-32 | Tạo một zip chỉ chứa thư mục `videos/` (thiếu `meta/`) và tải lên | Version "Không hợp lệ", lỗi "Không tìm thấy dataset LeRobot trong file nén…" hướng dẫn nén đúng thư mục | |

## 5. Train

| ID | Thao tác | Kết quả mong đợi | Đạt? |
|---|---|---|---|
| UAT-33 ★ | Đếm số click: từ lúc chọn file (bắt đầu một lượt tải mới của rar vào dataset tạm) → bấm "Train với version này" trong thông báo → Tiếp → Bắt đầu train | **≤ 5 click** sau khi chọn file; ACT được đánh dấu Khuyên dùng, preset Chuẩn được chọn sẵn | |
| UAT-34 ★ | Hủy lượt train vừa tạo ở UAT-33. Tạo lượt train mới: dataset `so101_picknplace` v1, ACT, preset **Nhanh**, GPU Tự động | Bước Xem lại hiện: tham số khác mặc định, ước tính VRAM ~1,8 GB / 12 GB và thời gian (nguồn ước tính ghi rõ), các bước kiểm tra đều Đạt | |
| UAT-35 | Ở bước Tham số, đặt "Số action thực thi mỗi lần dự đoán" = 200 (> chunk 100) | Lỗi ngay tại trường; không sang bước sau được | |
| UAT-36 | Chọn policy TD-MPC | Thẻ bị vô hiệu với lý do "dataset không có tín hiệu reward" | |
| UAT-37 ★ | Bắt đầu train (ACT Nhanh) | Chuyển sang trang lượt train #N: Đang chờ → Đang chuẩn bị → Đang train, cập nhật trực tiếp; tiến độ bước/tổng, ETA | |
| UAT-38 ★ | Để trang mở ≥ 5 phút (qua Cloudflare) | Biểu đồ loss cập nhật liên tục, chỉ báo "Trực tiếp" không mất kết nối (hoặc tự kết nối lại và hết lỗi) | |
| UAT-39 ★ | Tab Metrics | Có khung "Đọc các con số này thế nào" **không tắt được**: loss thấp không có nghĩa robot làm được | |
| UAT-40 | Tab Log: tìm "loss"; tải log | Có kết quả tìm; file `.log` tải về đầy đủ | |
| UAT-41 ★ | Tạm dừng › "Ở checkpoint kế tiếp" | Trạng thái "Đang tạm dừng — sẽ dừng sau checkpoint ở bước 5000"; sau đó "Đã tạm dừng", GPU được trả (trang Hàng đợi GPU thấy rảnh) | |
| UAT-42 ★ | Chạy tiếp | Vào hàng đợi rồi train tiếp từ bước 5000 (không từ 0); log có vạch "Bắt đầu lần chạy 2" | |
| UAT-43 | Cùng lúc tạo thêm một lượt train ACT với tài khoản B | Lượt của B chờ hoặc chạy trên GPU còn lại; trang Hàng đợi hiện thứ tự và chú thích fair-share | |
| UAT-44 | Tạo lượt train ACT trên GPU `cuda1` (Tesla P40) với Mixed precision = bf16 | Cảnh báo (không phải lỗi): P40 không có half precision nhanh, sẽ dùng fp32 | |
| UAT-45 ★ | Tạo lượt train ACT trên RTX 3060 với batch size 512, `dim_model` 2048 | Hoặc bị chặn ở bước kiểm tra "Không đủ bộ nhớ GPU" kèm gợi ý; hoặc nếu chạy, thất bại với lý do "GPU hết bộ nhớ…" và nút "Sao chép với batch size giảm một nửa" | |
| UAT-46 | Hủy một lượt đang train | Hỏi xác nhận nêu hậu quả; trạng thái Đang hủy → Đã hủy | |
| UAT-47 ★ | Đợi lượt ACT Nhanh (UAT-37) xong | Thành công; thẻ tóm tắt có loss cuối, MAE trên episode giữ lại **kèm câu "KHÔNG phải tỉ lệ thành công trên robot"**; model đang đóng gói → Sẵn sàng | |
| UAT-48 | Chọn 2 lượt train trong danh sách › So sánh | Biểu đồ chồng, mỗi lượt khác kiểu nét; bảng cấu hình chỉ hiện chỗ khác | |

## 6. Model và chạy trên robot

| ID | Thao tác | Kết quả mong đợi | Đạt? |
|---|---|---|---|
| UAT-49 ★ | Mở model của UAT-47 | Huy hiệu "Đã kiểm chứng" với 3 mục Đạt (nạp được trong LeRobot, MANIFEST khớp, ONNX khớp PyTorch, có số sai lệch); có câu "không có nghĩa robot sẽ làm được task" | |
| UAT-50 ★ | Tải bundle (.zip) trên trình duyệt, giải nén | Có `pretrained_model/`, `onnx/`, `eval/`, `logs/`, `run_on_robot.sh`, `MODEL_CARD.md`, `MANIFEST.json` | |
| UAT-51 ★ | Máy B: `hibiscus pull <tên model> --to ~/lelab/models` | Tải xong, kiểm tra sha256 khớp; thư mục `~/lelab/models/<tên>/pretrained_model/config.json` tồn tại | |
| UAT-52 ★ | Máy B: `source ~/lelab/leLab/.venv/bin/activate`; `lerobot-find-port`; trong thư mục bundle sửa `ROBOT_ID` cho đúng tên calibration; **tay để gần công tắc nguồn**; `PORT=/dev/ttyACM0 ./run_on_robot.sh` | `lerobot-rollout` khởi động, nạp policy từ `pretrained_model`, mở camera cổ tay, tay robot cử động theo policy trong 60 giây rồi dừng | |
| UAT-53 | Đánh giá bằng mắt: robot có gắp-thả được không (thử 5 lần) | Ghi tỉ lệ thành công **thực tế**. Đây là con số duy nhất nói lên chất lượng model; so với MAE offline để thấy hai con số khác nhau | |
| UAT-54 | (Tùy chọn) `python onnx/infer_onnx.py --bundle . --selftest` trong venv có numpy + onnxruntime | In action và độ trễ, thoát mã 0 | |
| UAT-55 | (Tùy chọn) Lưu token Hugging Face, Đẩy lên Hub repo riêng tư | Repo có `config.json`, `model.safetensors`, `README.md` (model card) | |

## 7. Thông báo, lỗi và khả năng tiếp cận

| ID | Thao tác | Kết quả mong đợi | Đạt? |
|---|---|---|---|
| UAT-56 ✉ | Tài khoản › Kênh thông báo › thêm Email (hoặc Discord), Gửi tin thử | Nhận được tin thử; khi một lượt train xong/lỗi thì nhận thông báo tương ứng | |
| UAT-57 | Thu hồi token ở UAT-20, rồi trên máy B chạy `hibiscus push …` | CLI báo "Token truy cập đã bị thu hồi" và chỉ chỗ tạo token mới | |
| UAT-58 ★ | Dùng **chỉ bàn phím** (Tab, Shift+Tab, Enter, Space, mũi tên) làm lại: đăng nhập + 2FA, tạo lượt train qua trình hướng dẫn, mở trang lượt train, tạm dừng | Làm được hết; luôn thấy rõ ô đang được focus; hộp thoại giữ focus bên trong và trả focus khi đóng | |
| UAT-59 | Phóng to trình duyệt 200 % ở trang trình hướng dẫn và trang lượt train | Không mất chữ, không nút nào bị che; bảng/biểu đồ cuộn trong khung riêng | |
| UAT-60 | Mở trang trên điện thoại (hoặc chế độ giả lập 375 px): danh sách lượt train, trang lượt train, trang model | Dùng được bằng một tay; bảng thành dạng thẻ; nút Tải về và lệnh chạy robot sao chép được | |
| UAT-61 | Bất kỳ thông báo lỗi nào gặp trong UAT | Có tiêu đề, giải thích việc cần làm (không phải mã lỗi trơn), có "Mã yêu cầu" sao chép được khi là lỗi máy chủ | |

## 8. Bảng ghi kết quả

| ID | Đạt / Không đạt | Ghi chú / ảnh |
|---|---|---|
| UAT-01 … UAT-61 | | |

**Tiêu chí nghiệm thu**: mọi bước ★ đạt; ≤ 3 bước không có ★ không đạt và đều có ticket sửa với
người phụ trách (theo `docs/OWNERSHIP.md`). Ký nghiệm thu: ____________  Ngày: __________
