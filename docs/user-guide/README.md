# Hướng dẫn sử dụng Hibiscus / Hibiscus user guide

Hibiscus là nền tảng train policy LeRobot trên GPU của lab, dùng qua trình duyệt tại
**https://robot.example.com** — không cần cài gì để dùng giao diện web. Máy collect cạnh robot
dùng thêm CLI `hibiscus` để đẩy dataset lên và kéo model về.

Hibiscus trains LeRobot policies on the lab GPUs. Use it from any browser at
**https://robot.example.com** — nothing to install. The collection machine next to the robot
additionally uses the `hibiscus` CLI.

| # | Tiếng Việt (chính) | English |
|---|---|---|
| 1 | [Bắt đầu: tài khoản, bảo mật, workspace](vi/01-bat-dau.md) | [Getting started](en/01-getting-started.md) |
| 2 | [Dataset: tải lên, kiểm tra, xem trước](vi/02-dataset.md) | [Datasets](en/02-datasets.md) |
| 3 | [CLI trên máy collect](vi/03-cli-may-collect.md) | [CLI on the collection machine](en/03-cli.md) |
| 4 | [Train model](vi/04-train.md) | [Training](en/04-training.md) |
| 5 | [Đọc metrics cho đúng](vi/05-doc-metrics.md) | [Reading metrics honestly](en/05-metrics.md) |
| 6 | [Chạy model trên robot](vi/06-chay-tren-robot.md) | [Running a model on the robot](en/06-run-on-robot.md) |
| 7 | [Team, token và quản trị](vi/07-team-quan-tri.md) | [Team, tokens and administration](en/07-team-admin.md) |
| 8 | [Xử lý sự cố](vi/08-xu-ly-su-co.md) | [Troubleshooting](en/08-troubleshooting.md) |

Luồng chính trong 6 bước / the main journey in six steps:

```
thu dữ liệu (LeLab/lerobot-record) → hibiscus push → kiểm tra tự động → train (web hoặc hibiscus train)
→ tải bundle (web hoặc hibiscus pull) → ./run_on_robot.sh trong venv LeLab
```

> Ảnh chụp màn hình sẽ được bổ sung sau khi giao diện hoàn thiện (Phase 4). Hiện tại tên nút và
> bố cục tham chiếu theo `docs/ux/wireframes.md`; tên nút trong hướng dẫn trùng với chữ trên giao diện.
> Screenshots will be added once the UI is final (Phase 4).
