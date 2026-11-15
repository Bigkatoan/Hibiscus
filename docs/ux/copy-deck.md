# UX copy deck (vi / en)

The wording itself lives in `frontend/src/i18n/{vi,en}/translation.json` (the single source of
truth the app loads; 851 keys in en, 848 in vi because vi has no `_one` plural forms). This deck defines **how** to write it, the shared vocabulary, and the patterns A6 must
follow when placing copy. Error wording: `error-catalogue.md` (generated). Key rules:
`i18n-conventions.md`.

## 1. Voice and tone

| Principle | vi | en |
|---|---|---|
| Address | "bạn"; no "quý khách", no "chúng tôi xin lỗi vì sự bất tiện" | "you"; plain, no "Oops!" |
| Say what happened, then what to do | "GPU hết bộ nhớ. Hãy giảm batch size một nửa…" | "The GPU ran out of memory. Halve the batch size…" |
| Blame the system, not the user | "Máy chủ không đọc được yêu cầu" | "The server could not read this request" |
| Honest about ML | Never imply that low loss / verified = robot success | same |
| Short | Titles ≤ 6 words, buttons 1–3 words (verb first) | same |
| No jargon in chrome, exact jargon in ML | "Tải lên", but keep "batch size", "checkpoint" | same |
| Safety first near hardware | Explicit warning before first robot run | same |

Sentence case everywhere in English ("Start training", not "Start Training"). Vietnamese:
capitalise only the first word and proper nouns.

## 2. Glossary (canonical terms)

| Concept | en (UI) | vi (UI) | Notes |
|---|---|---|---|
| run | run / training run | lượt train | never "job" for runs; "job" = background task (`jobs.*`) = "tác vụ nền" |
| dataset version | version | version | keep "version", not "phiên bản", to match `v2` labels |
| episode | episode | episode | |
| frame | frame | frame | |
| policy | policy | policy | model architecture choice (ACT, Diffusion…) |
| model / bundle | model, model bundle | model, bundle model | "bundle" = the downloadable zip |
| checkpoint | checkpoint | checkpoint | |
| held-out episodes | held-out episodes | episode giữ lại (để đánh giá) | |
| offline evaluation | offline evaluation | đánh giá offline | always with disclaimer |
| verified | Verified | Đã kiểm chứng | 3 technical checks only |
| preset | preset | preset | Quick/Standard/Fine-tune = Nhanh/Chuẩn/Tinh chỉnh |
| hyperparameters | settings | tham số / cấu hình | "Settings" step in wizard = "Tham số" |
| queue | GPU queue | hàng đợi GPU | |
| fair-share | fair-share | fair-share | explained once in `workspace.queue.fair_share` |
| workspace | workspace | workspace | |
| owner/admin/member/viewer | Owner/Admin/Member/Viewer | Chủ sở hữu/Quản trị/Thành viên/Người xem | |
| platform admin | Platform admin | Quản trị hệ thống | |
| PAT | personal access token / access token | token truy cập (PAT) | |
| two-factor authentication | two-factor authentication | xác thực hai lớp | not "2FA" in prose; "2FA" allowed in narrow table headers |
| recovery code | recovery code | mã khôi phục | |
| upload / download | upload / download | tải lên / tải về (tải xuống on buttons) | |
| validate / validation | validate / validation | kiểm tra | not "xác thực" (that is auth) |
| collection machine | collection machine | máy collect | the PC next to the robot ("machine B") |
| mixed precision / fp32 | mixed precision / full precision (fp32) | mixed precision / độ chính xác đầy đủ (fp32) | |
| out of memory | out of memory | hết bộ nhớ | |
| loss | loss | loss | "Training loss" = "Loss khi train" |
| learning rate, batch size | unchanged | unchanged | |
| fingerprint (sha256) | fingerprint | dấu vân tay | technical value shown beside it |

Product names are never translated: Hibiscus, LeRobot, LeLab, Hugging Face, Cloudflare, ONNX,
RTX 3060, Tesla P40, ACT, SmolVLA, Pi0, Pi0.5, VQ-BeT, TD-MPC.

## 3. Patterns

### 3.1 Buttons and links
* Verb + object when the object is not obvious: "Upload dataset", "Revoke token".
* Destructive actions name the thing: "Delete dataset", never just "Delete" in a confirm dialog.
* The confirm button repeats the action verb ("Cancel run"). The dismiss button is
  `common.cancel`, **except** when the action itself is a cancel (cancel run, cancel
  upload, cancel job): then the dismiss button uses `common.close` to avoid a
  "Cancel / Cancel run" pair.

### 3.2 Confirmation dialogs
Title = question with the object ("Cancel run #42?"), body = consequence + what is kept
(`*_confirm` keys already contain both). Type-to-confirm (not built yet)
only for: delete workspace, delete dataset with versions in use history, admin disable user.

### 3.3 Toasts
Success toasts: past tense, ≤ 1 line (`tokens.revoked`). Errors from background actions
use the error title as toast title and the message as body, with request id. Toasts never carry
the only copy of important information (warnings live on the page).

### 3.4 Empty states
Title (what is missing) + body (why it matters / how to get it) + one primary action; role-aware
variant for viewers (no action). Include the CLI equivalent for datasets.

### 3.5 Loading
"Loading…" text only for screen readers / after 300 ms; skeletons for lists. Long processes say
what is happening and that the user may leave (`upload.done`,
`upload.description`). Never show fake percentages (preparing, validating without
progress data).

### 3.6 Numbers and units
`Intl.NumberFormat(locale)`; GiB/MiB binary; durations "1 h 12 min" (en) / "1 giờ 12 phút" (vi)
via `Intl.DurationFormat` or a small helper; steps with thousands separators ("61,000" /
"61.000"); learning rates in scientific notation (`1e-5`) as LeRobot prints them; metric values
to 3 significant digits.

### 3.7 Dates
Relative for < 7 days (`Intl.RelativeTimeFormat`), absolute otherwise; absolute in tooltip/`<time
datetime>` always. Timezone: browser local, with UTC offset in tooltip.

### 3.8 Code and commands
Shown in `<code>`/`<pre>` blocks with a Copy button (`common.copy`), never
inside translated sentences that could be reflowed. Commands are identical in vi and en.

## 4. Error message usage (normative for A6)

Keys below are in `frontend/src/i18n/{vi,en}/translation.json`; full table in
`i18n-conventions.md` §3, wording per code in `error-catalogue.md`.

1. Branch on `Problem.code` only: `errors.<code>` is one sentence that says what happened **and
   what to do next** (`src/lib/errors.ts`, rendered by `ErrorAlert`). `retry_after_s` and
   `Problem.params` are interpolated (`errors.rate_limited`, `errors.account_locked`).
2. Show `errors.request_id` with `Problem.request_id` (always for 5xx, `internal_error`,
   `conflict` and unknown codes). Unknown codes fall back to `errors.unknown_error`.
3. Field-level: `Problem.errors[]` → `field_errors.<code>` next to the field (fallback
   `errors.<Problem.code>`); the field label already names the field.
4. Preflight rows: label `preflight.check.<id>`, text `preflight.code.<code>` → `errors.<code>` →
   `run.warning.<code>`.
5. Validation issues: `validation.issue.<code>` (interpolates `episode`, `feature`, `path`).
6. Run failure: `run.error.<error_code>` + log excerpt.
7. Server `detail`/`message` (English) may be shown only inside a technical-detail area,
   `lang="en"`.

## 5. Copy for the honesty requirements (PLAN §3.5, §3.6)

These strings must appear wherever the related number is shown and must not be dismissible:
* `eval.offline_not_success_rate` — every place an eval MAE/MSE is shown (run summary, eval tab,
  compare eval table, model detail, model card).
* `model.verification_help` — next to the verified badge.
* `run.metrics_honesty.title` / `.body` — permanent box at the top of the Metrics tab (low
  offline loss ≠ robot success; UAT-39).
* `model.run_on_robot.no_inference` — first thing in the model page's "Run it on the robot" card
  (LeLab has no inference; use `run_on_robot.sh` / the LeRobot CLI in the LeLab venv; UAT-49/60),
  followed by the copyable steps and `model.run_on_robot.safety`.
* `model.verified_not_success` — appended to `model.verification_help` (verified ≠ the robot
  succeeds at the task).

## 6. Email copy (Cloudflare Email Service, sender owned by A2/A8)

Emails are sent by the `cloudflare` EmailSender provider (decision CONTRACT_NOTES §4.1). A7
proposes the subject/body copy below; A2 owns the templates (not in `frontend/src/i18n`). Plain
text first, HTML optional; link on its own line; no tracking pixels; sender display name
"Hibiscus".

| Template | Subject (vi / en) | Body essentials |
|---|---|---|
| invite | "{inviter} mời bạn vào {workspace} trên Hibiscus" / "{inviter} invited you to {workspace} on Hibiscus" | role, link, "valid 72 hours, single use", "if you did not expect this, ignore it" |
| verify email | "Xác thực email Hibiscus" / "Verify your Hibiscus email" | link, validity |
| password reset | "Đặt lại mật khẩu Hibiscus" / "Reset your Hibiscus password" | link, validity, "all sessions will be signed out", "ignore if not you" |
| run finished / failed / stalled | "Lượt train #{n} đã xong" / "Run #{n} finished" etc. | same text as `notifications.kind.*`, link to run |
| model ready | "Model {name} đã sẵn sàng" / "Model {name} is ready" | link, verified status, disclaimer |

Email language = recipient's `User.locale` (invite: inviter's workspace default, else vi).
