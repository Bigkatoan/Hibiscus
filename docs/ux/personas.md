# Personas

Three people use Hibiscus in v1. They share two GPUs (RTX 3060 12 GB, Tesla P40 24 GB) on one
machine that is reachable from the internet at `https://robot.example.com`. Each persona lists
what they need, what scares them, and which flows in `user-flows.md` are theirs.

---

## P1 — Lab owner ("Khoa")

| | |
|---|---|
| Role | Platform admin + `owner` of the lab workspace. Owns the GPU machine and the domain. |
| Background | Robotics engineer, comfortable with Linux, Docker, LeRobot CLI and Cloudflare dashboard. Writes Vietnamese day to day, reads English docs. |
| Devices | Desktop browser on the lab LAN and from home; phone for 2FA. |
| Goals | Turn recorded SO-101 demonstrations into a model that runs on the robot with as few manual steps as possible; let 2–5 teammates train without giving them shell access; keep the internet-facing box safe. |
| Pain today | Training means SSH + long `lerobot-train` commands; LeLab's training form uses outdated flags; nobody knows which GPU is free; a `.rar` from the collection PC could not be opened with p7zip; LeLab cannot run a policy. |
| Fears | Someone breaking in through the public URL; a teammate's run monopolising both GPUs; losing a 3-hour run to a crash; a model that "looks good" (low loss) but fails on the robot. |
| Success | Invites the team in minutes; sees at a glance who is using which GPU; every run is reproducible; downloads a *verified* bundle and runs `run_on_robot.sh` in the LeLab venv. |
| Key flows | F1 bootstrap, F2 invite/roles, F3 2FA, F12 admin, F13 quotas/GPUs, F7 compare, F0 primary journey. |
| Design implications | Admin needs dense tables and audit log; 2FA must never be skippable for this role; email may be off (Cloudflare Email Service not yet verified) so every email flow needs a copy-link fallback. |

## P2 — Team member ("Linh")

| | |
|---|---|
| Role | `member` of the lab workspace. |
| Background | Master's student in ML. Knows PyTorch and what loss curves are; new to LeRobot internals and to robot hardware. Prefers Vietnamese UI but English technical terms. |
| Devices | Laptop browser, sometimes over slow home internet. |
| Goals | Try ACT vs Diffusion vs SmolVLA on the same dataset, tune a few hyperparameters, compare runs, hand the best model to whoever operates the robot. |
| Pain today | Doesn't know which flags are valid for which policy; OOM after waiting an hour; can't tell if the P40 is "bad" or her config is wrong. |
| Fears | Wasting GPU hours of the whole team; misreading metrics; breaking a shared dataset. |
| Success | A form that only offers valid options with explanations, an upfront VRAM/time estimate, clear failure reasons ("halve batch size"), side-by-side comparison with config diff, honest evaluation wording. |
| Key flows | F5 wizard, F6 live run, F7 compare, F8 checkpoints/export, F9 models, F10 errors. |
| Design implications | Basic/Advanced split; every field has `label` + `help`; preflight blocks before queueing; metrics page carries the "offline loss ≠ robot success" note permanently, not as a dismissible toast. |

## P3 — Data-collection operator ("Tuấn")

| | |
|---|---|
| Role | `member` (or a PAT on the collection machine with `datasets:write`, `runs:write`, `models:read`). |
| Background | Technician who teleoperates the leader arm and records episodes with LeLab / `lerobot-record` on "machine B" (the collection PC next to the robot). Comfortable in a terminal for copy-pasted commands; not an ML person. |
| Devices | Collection PC (Linux, LeLab venv at `~/lelab/leLab/.venv`), unstable lab Wi-Fi, phone. |
| Goals | After a recording session, get the data to the server without USB sticks, start the standard training, and later pull the model back to the same PC to try it on the robot. |
| Pain today | Copying multi-GB archives by hand; uploads die on Wi-Fi drops; finding out hours later that one episode's video was truncated. |
| Fears | Typing a wrong command and deleting data; the robot moving unexpectedly when running a policy. |
| Success | `hibiscus push ./my_dataset --name picknplace` resumes after drops and tells him if the data is valid; `hibiscus pull` puts the model where LeRobot finds it; `run_on_robot.sh` only needs the serial port. |
| Key flows | F4 upload (CLI), F0 primary journey, F11 run on robot, F4e validation errors. |
| Design implications | CLI output must be bilingual-friendly plain text with the same codes/messages as the UI; validation issues must say *which episode* and *what to do* (re-record / delete); safety note before first robot run. |

---

## Anti-personas (explicitly not served in v1)

* Anonymous public visitors — registration is invite-only; the login page shows nothing else.
* Users wanting simulation evaluation, multi-node training, TensorRT/Jetson export (backlog).
* Users expecting LeLab to run the policy from its UI — LeLab has no inference; we never claim it
  does (ADR-0011).

## Accessibility profiles considered

Keyboard-only use (Linh uses a tiling WM), low vision / 200 % zoom (Khoa on a 4K screen), colour
vision deficiency (status must not rely on red/green), screen reader spot checks (NVDA/Firefox,
VoiceOver/Safari). See `accessibility.md`.
