# 6. Chạy model trên robot

> **LeLab hiện chưa có chức năng chạy policy.** Hibiscus không sửa LeLab. Thay vào đó bạn chạy
> model bằng **LeRobot CLI** (`lerobot-rollout`) ngay **trong venv của LeLab**
> (`~/lelab/leLab/.venv`, đã có sẵn LeRobot 0.7.1) — không cần cài thêm gì. Khi LeLab bản gốc có
> tính năng chạy policy, bundle vẫn dùng được vì đúng chuẩn LeRobot.

## 6.1 Trong bundle có gì

```
so101_picknplace_act-r42-step100000/
├── pretrained_model/     # thư mục policy chuẩn LeRobot → dùng với --policy.path
├── onnx/                 # model ONNX + infer_onnx.py (chỉ ACT, Diffusion; xem 6.5)
├── eval/                 # đánh giá offline + đồ thị
├── logs/                 # train.log, metrics.csv
├── run_on_robot.sh       # lệnh lerobot-rollout dựng sẵn
├── MODEL_CARD.md         # đã train gì, thế nào, kết quả, cách chạy
└── MANIFEST.json         # dấu vân tay mọi file, version phần mềm
```

Lấy bundle bằng nút **Tải bundle (.zip)** trên trang model rồi giải nén, hoặc
`hibiscus pull <tên model> --to ~/lelab/models` (chương 3).

## 6.2 An toàn trước khi chạy

* Lần đầu chạy model mới: để tay gần **công tắc nguồn** của tay robot, dọn khu vực làm việc,
  không đứng trong tầm với của tay.
* Policy có thể di chuyển nhanh và bất ngờ, nhất là khi camera/ánh sáng khác lúc thu.
* Bắt đầu với thời gian ngắn: `DURATION=20 ./run_on_robot.sh`.

## 6.3 Chạy bằng `run_on_robot.sh`

```bash
cd ~/lelab/models/so101_picknplace_act-r42-step100000
source ~/lelab/leLab/.venv/bin/activate

# 1. Tìm cổng serial của tay follower (làm theo hướng dẫn: rút cáp USB rồi Enter)
lerobot-find-port

# 2. (nếu chưa biết chỉ số camera)
lerobot-find-cameras opencv

# 3. Chạy: PORT, ROBOT_ID (tên calibration bạn đã dùng khi thu), chỉ số camera
PORT=/dev/ttyACM0 ROBOT_ID=my_follower WRIST_CAM=0 ./run_on_robot.sh
```

Script được sinh sẵn từ dataset (loại robot, fps, tên và độ phân giải camera, task đầu tiên). Nó
chạy lệnh tương đương:

```bash
lerobot-rollout \
  --strategy.type=base \
  --policy.path="$HERE/pretrained_model" \
  --robot.type=so101_follower \
  --robot.port="$PORT" --robot.id="$ROBOT_ID" \
  --robot.cameras="{ wrist_cam: {type: opencv, index_or_path: ${WRIST_CAM}, width: 640, height: 360, fps: 30} }" \
  --task="<task của dataset>" \
  --fps=30 --duration="${DURATION:-60}"
```

Biến môi trường dùng được: `PORT`, `ROBOT_ID`, một biến cho mỗi camera (tên camera viết hoa, ví
dụ `WRIST_CAM`), `DURATION` (giây, mặc định 60). Bạn cũng có thể sửa trực tiếp đầu file.

Tên camera trong `--robot.cameras` (ví dụ `wrist_cam`) **phải trùng** tên camera trong dataset
(`observation.images.wrist_cam`), nếu không policy sẽ báo thiếu input.

## 6.4 Dùng `pretrained_model/` với các lệnh LeRobot khác

`pretrained_model/` là thư mục chuẩn của LeRobot, dùng được ở bất kỳ đâu nhận `--policy.path`:

```bash
# vừa chạy policy vừa thu các episode đánh giá thành dataset mới (LeRobot 0.7.1)
lerobot-rollout --strategy.type=episodic \
  --policy.path=./pretrained_model \
  --robot.type=so101_follower --robot.port=/dev/ttyACM0 --robot.id=my_follower \
  --robot.cameras="{ wrist_cam: {type: opencv, index_or_path: 0, width: 640, height: 360, fps: 30} }" \
  --dataset.repo_id=<tên-bạn>/eval_so101_picknplace --dataset.single_task="<task>" \
  --dataset.num_episodes=10
```

Lưu ý: ở LeRobot 0.7.1, **`lerobot-record` không còn tham số `--policy`**; việc chạy policy (kể
cả khi thu dữ liệu) đi qua `lerobot-rollout`. Nếu bạn đẩy model lên Hugging Face Hub, có thể dùng
`--policy.path=<user>/<repo>` thay cho đường dẫn thư mục.

## 6.5 ONNX (không cần LeRobot)

Có với ACT và Diffusion (VQ-BeT có thể có ở v1.1; SmolVLA, Pi0, Pi0.5, TD-MPC không có ONNX ở v1).
Chỉ dùng khi huy hiệu ONNX là **parity đạt**.

```bash
cd <bundle>/onnx
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python infer_onnx.py --bundle .. --selftest   # in action + độ trễ, thoát mã 0 nếu ổn
```

`infer_onnx.py` có lớp `OnnxPolicy(bundle_dir)` với `.reset()` và `.select_action(obs)` để bạn
nhúng vào chương trình riêng; mô tả input/output ở `onnx/io_spec.json`.

## 6.6 Lỗi hay gặp

| Hiện tượng | Nguyên nhân / cách làm |
|---|---|
| `could not open port /dev/ttyACM0` | Sai cổng hoặc thiếu quyền: chạy lại `lerobot-find-port`; thêm user vào nhóm `dialout` rồi đăng nhập lại |
| LeRobot hỏi calibrate | `ROBOT_ID` không trùng tên calibration đã có; đặt đúng `ROBOT_ID` |
| Không mở được camera | Sai chỉ số: `lerobot-find-cameras opencv`; đóng LeLab/ứng dụng khác đang giữ camera |
| Lỗi thiếu feature `observation.images.<tên>` | Tên camera trong script khác tên trong dataset — sửa cho trùng |
| Robot giật hoặc đứng yên | Ánh sáng/vị trí camera khác lúc thu; thử `DURATION` ngắn, kiểm tra camera nhìn đúng như khi thu. Chất lượng hành vi phụ thuộc dữ liệu (chương 5) |
| Chạy rất chậm trên máy không có GPU | Policy lớn (SmolVLA, Pi0) cần GPU; ACT chạy được trên CPU nhưng chậm hơn |
