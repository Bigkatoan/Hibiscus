# hibiscus — Hibiscus CLI

*[Tiếng Việt](#tiếng-việt) · [English](#english)*

`hibiscus` chạy trên máy collect (Python ≥ 3.10) và nói chuyện với Hibiscus qua API
`https://robot.example.com/api/v1` bằng Personal Access Token (PAT).

```
hibiscus login                                   # lưu PAT (keyring, hoặc file 0600)
hibiscus push ~/lerobot_data/so101_picknplace    # upload thư mục hoặc .zip/.tar/.tar.zst/.rar, resume được
hibiscus watch ~/lerobot_data                    # tự upload mỗi recording đã xong, đúng 1 lần
hibiscus datasets ls | show <tên>
hibiscus train -d so101_picknplace -p act --preset standard --set steps=300 -f
hibiscus runs ls | show '#42'
hibiscus logs -f '#42'                           # SSE, tự nối lại với Last-Event-ID
hibiscus models ls
hibiscus pull <model> --to ~/models              # kiểm tra sha256 từng file theo MANIFEST.json
```

---

## Tiếng Việt

### Cài đặt

```bash
# từ repo (khuyên dùng uv)
cd Hibiscus/cli && uv tool install .        # hoặc: pipx install .  /  pip install .
hibiscus --version
```

Phụ thuộc runtime: `typer`, `httpx`, `rich`, `keyring`, `platformdirs`, `attrs`, `python-dateutil`.
Không cần LeRobot, torch hay pyarrow.

### Đăng nhập

1. Trên web: **Cài đặt → Token → Tạo token**, chọn workspace và scope:
   `datasets:write` (push/watch), `runs:write` (train), `runs:read` (logs/runs), `models:read` (pull).
2. `hibiscus login` rồi dán token (không hiện trên màn hình). Mặc định server là
   `https://robot.example.com`; dùng `--server http://127.0.0.1:18000` khi chạy trên chính máy GPU.

Token được lưu trong **OS keyring** (GNOME Keyring / KWallet / macOS Keychain). Máy không có keyring
(SSH, headless) → tự dùng `~/.config/hibiscus/credentials.json` với quyền **0600** (CLI từ chối đọc
nếu file bị đọc được bởi user khác). Biến môi trường `HIBISCUS_TOKEN` (CI) được ưu tiên và không bao
giờ được ghi ra đĩa; `HIBISCUS_KEYRING=0` để tắt keyring. `hibiscus logout` xoá token.

### Upload dataset — `hibiscus push`

```bash
hibiscus push ~/data/so101_picknplace                 # dataset mới tên "so101_picknplace"
hibiscus push ~/data/so101_picknplace --name pick_v2  # đặt tên khác
hibiscus push ~/data/day2 --dataset so101_picknplace  # thêm version mới cho dataset có sẵn
hibiscus push Picknplace_20261114_221710.rar --wait   # gửi archive, đợi validate xong
```

* Thư mục được đóng gói thành **tar ảo**: không tạo file tạm, không tốn thêm ổ đĩa; tar có thứ tự
  cố định nên sha256 giống nhau giữa các lần chạy (bỏ qua `.cache`, `.git`, `__pycache__`;
  thêm `--exclude TÊN`).
* Chia **part ≤ 64 MiB** (giới hạn 100 MB/request của Cloudflare), mỗi part kèm `X-Content-SHA256`,
  gửi song song `-j 2`, tự retry với backoff 1, 2, 4 … 60 s (lỗi mạng, 5xx, 429 + `Retry-After`).
* **Resume**: bị ngắt (mất mạng, Ctrl-C, mất điện) thì chạy lại **đúng lệnh cũ**. CLI đọc file trạng
  thái `~/.local/state/hibiscus/uploads/*.json`, hỏi server các part đã nhận và chỉ gửi phần còn thiếu.
  Nếu file nguồn thay đổi, CLI bắt đầu lại từ đầu; nếu file thay đổi *trong lúc* upload, CLI dừng.
* Xong: server xác minh sha256 toàn bộ và chạy job validate (`hibiscus datasets show <tên>`).

### Tự upload khi record xong — `hibiscus watch`

```bash
hibiscus watch ~/lerobot_data --debounce 30          # mỗi recording -> dataset mới (tên thư mục)
hibiscus watch ~/lerobot_data --dataset so101_picknplace   # mọi recording -> version của 1 dataset
```

Một recording LeRobot v3.0 được coi là **xong** khi `dataset.finalize()` đã chạy: `meta/info.json`
(v3.x, `total_episodes ≥ 1`), `meta/stats.json`, `meta/tasks.parquet`, các parquet có footer `PAR1`
(writer đã đóng), mọi mp4 có `moov` (encoder đã đóng), thư mục tạm `images/` trống, **và** không có file
nào thay đổi trong `--debounce` giây. Mỗi recording chỉ upload **một lần** (sổ ghi
`~/.local/state/hibiscus/watch-ledger.json`); record thêm episode → upload lại thành version mới của
cùng dataset. `--once` quét đến khi không còn gì đang chờ rồi thoát (hợp với cron/systemd timer).

### Train — `hibiscus train`

```bash
hibiscus train -d so101_picknplace -p act --preset quick
hibiscus train -d so101_picknplace -v 2 -p act --preset standard \
  --set steps=20000 --set chunk_size=50 --set train.batch_size=16 --gpu cuda1 --follow
hibiscus train -d so101_picknplace -p act --preflight-only
```

* `--set key=value`: `policy.X` / `train.X`, hoặc tên trần (tự tra trong JSON Schema của policy/train
  từ server). Giá trị đọc như JSON (`true`, `null`, `0.5`, `[1,2]`), không được thì là chuỗi.
* Luôn chạy **preflight** trước; có lỗi (VRAM, camera không khớp, …) thì dừng và in lý do.
* `--follow` / `-f` theo dõi log ngay sau khi tạo run.

### Log — `hibiscus logs`

`hibiscus logs '#42'` in log đã lưu; `-n 50` chỉ 50 dòng cuối; `-f` theo dõi trực tiếp qua SSE đến khi run
kết thúc. Mất kết nối (Cloudflare cắt, Wi-Fi rớt) → tự nối lại sau `retry` của server (3 s, tăng dần
đến 30 s) với `Last-Event-ID`, nên không mất/không lặp sự kiện status/metrics; các dòng log bị lỡ
trong lúc mất kết nối được lấy lại bằng `Range`. Mã thoát: **0** nếu run `succeeded`, **1** nếu khác.
`--metrics` in thêm metric.

### Tải model — `hibiscus pull`

```bash
hibiscus pull so101_picknplace_act-42-step10000 --to ~/models
hibiscus pull <model-id> --to ~/models --only pretrained_model      # chỉ lấy phần LeRobot cần
```

Tải zip bundle (resume bằng `Range` + `If-Range`), kiểm tra sha256 zip = `bundle_sha256`, giải nén an
toàn (chặn `..`, đường dẫn tuyệt đối, symlink), rồi kiểm tra **mọi file theo `MANIFEST.json`** (size +
sha256, không thừa/thiếu). Chỉ khi đạt mới đổi tên vào `<to>/<bundle_name>/`. Dùng ngay với LeRobot/LeLab:

```bash
source ~/lelab/leLab/.venv/bin/activate
lerobot-rollout --policy.path=~/models/<bundle_name>/pretrained_model ...   # hoặc ./run_on_robot.sh
```

### Biến môi trường

| Biến | Ý nghĩa |
|---|---|
| `HIBISCUS_SERVER` | URL server (như `--server`) |
| `HIBISCUS_TOKEN` | PAT (không lưu xuống đĩa) |
| `HIBISCUS_WORKSPACE_ID` | ghi đè workspace đã lưu |
| `HIBISCUS_KEYRING=0` | không dùng keyring, chỉ dùng file 0600 |
| `HIBISCUS_CONFIG_DIR` / `HIBISCUS_STATE_DIR` | đổi thư mục cấu hình / trạng thái |

---

## English

### Install

```bash
cd Hibiscus/cli && uv tool install .      # or: pipx install . / pip install .
```

Python ≥ 3.10. No LeRobot / torch / pyarrow needed on the collect machine.

### Authenticate

Create a PAT in the web UI (**Settings → Tokens**) bound to one workspace with the scopes you need
(`datasets:write` for push/watch, `runs:write` for train, `runs:read` for logs/runs, `models:read` for
pull), then run `hibiscus login` and paste it (hidden input). The token goes to the OS keyring; on hosts
without a usable keyring it is stored in `~/.config/hibiscus/credentials.json` with mode 0600 (refused if
group/other-readable). `HIBISCUS_TOKEN` overrides both and is never persisted.

### Commands

| Command | What it does | API operations |
|---|---|---|
| `login` / `whoami` / `logout` | store / show / delete the PAT | `getMe` |
| `push <dir\|archive>` | resumable chunked upload (≤ 64 MiB parts, per-part sha256, retries, `--wait`) | `initUpload`, `getUpload`, `uploadPart`, `completeUpload`, `getDatasetVersion` |
| `watch <dir>` | upload each finished LeRobot v3.0 recording once (debounced) | as `push` |
| `datasets ls` / `show` | list / inspect datasets and versions | `listDatasets`, `getDataset`, `listDatasetVersions`, `getDatasetVersion` |
| `train` | preflight + create a run (`--preset`, `--set key=value`, `--follow`) | `getPolicy`, `preflightRun`, `createRun` |
| `runs ls` / `show` | list / inspect runs (`#42` or id) | `listRuns`, `getRun` |
| `logs [-f] <run>` | print / follow logs; SSE reconnect with `Last-Event-ID`, gap fill via `Range` | `getRunLogs`, `streamRunEvents` |
| `models ls` | list model bundles | `listModels` |
| `pull <model> --to <dir>` | download (Range resume), verify zip sha256 and every file against MANIFEST.json | `getModel`, `downloadModel`, `listModelFiles`, `getModelFile` |

Every listing command accepts `--json` for scripting.

**Resuming uploads.** Re-run the same `hibiscus push` command. The resume state
(`~/.local/state/hibiscus/uploads/<key>.json`, 0600) caches the archive hashes and the upload id; the
client asks the server which parts it already holds (with their sha256) and sends only the rest.
Directories are streamed as a deterministic *virtual tar* (no staging copy; same bytes every run), so
resuming works across reboots. A changed source restarts the upload; a source modified *during* an
upload aborts it.

**Recording detection.** A recording is complete when `meta/info.json` (v3.x, ≥ 1 episode),
`meta/stats.json`, `meta/tasks.parquet`, the episode and data parquet files exist and all parquet files
have their `PAR1` footer, every mp4 has a `moov` box, `images/` is empty, and nothing changed for
`--debounce` seconds.

### Development

```bash
cd cli
env -u PYTHONPATH uv sync                       # ROS hosts: drop the ROS PYTHONPATH
env -u PYTHONPATH uv run poe gen-api            # regenerate hibiscus/_generated from ../api/openapi.yaml
env -u PYTHONPATH uv run poe check-api          # fail if the generated client is stale
env -u PYTHONPATH uv run ruff check . && env -u PYTHONPATH uv run ruff format --check .
env -u PYTHONPATH uv run mypy hibiscus tests scripts
env -u PYTHONPATH uv run pytest --cov
```

`hibiscus/_generated/` is produced by `openapi-python-client==0.26.2` (pinned: newer versions emit
`typing.Self`, which needs Python 3.11) and is never edited by hand; `hibiscus/api.py` is the thin
hand-written layer. Byte-stream operations (`uploadPart`, downloads, SSE, log `Range`) use `httpx`
directly because the generator cannot express them for this contract (see `docs/handoff/A9-cli.md`).

Tests run against a stateful fake server mounted on `respx` (`tests/fake_server.py`): every request is
matched to an OpenAPI operation and every JSON request/response is validated against
`api/openapi.yaml`. They include interrupted-upload resume, lost responses, retries/backoff, SSE
reconnect with `Last-Event-ID`, Range-resumed downloads, tampered bundles, and two tests on the real
golden data (the 144.8 MB RAR5 archive in 3 parts; the golden dataset directory tarred and re-extracted).
