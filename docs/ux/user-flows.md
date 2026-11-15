# User flows

Every PLAN v1 feature as an end-to-end flow, with the API operations behind each step
(`operationId` from `api/openapi.yaml`), the i18n keys for the important copy, and the error,
empty and loading states. Screens referenced as **S-xx** are drawn in `wireframes.md`.
Personas: P1 lab owner, P2 team member, P3 collection operator (`personas.md`).

Notation: `→` user action, `⇒` system response, `[code]` = `Problem.code` / enum value.

---

## F0 — Primary journey: collect on machine B → push → train → download → run on robot

Actors: P3 on the collection PC ("machine B", LeLab venv), P2/P3 in the browser, Hibiscus server.

```
 machine B (robot PC)                  Hibiscus (robot.example.com)                 machine B
 ───────────────────                   ─────────────────────────────                 ─────────
 lerobot-record / LeLab ──┐
                          ▼
 hibiscus push ./ds ──chunks≤64MiB──▶ initUpload/uploadPart/completeUpload
                                       ⇒ unpack (sandbox) ⇒ validate 7 steps ⇒ ready
                                       ⇒ notification dataset.ready
 hibiscus train --preset standard ───▶ preflightRun ⇒ createRun ⇒ queue ⇒ GPU
 hibiscus logs -f #42 ◀── SSE ──────── streamRunEvents (status/progress/metrics)
                                       ⇒ exporting ⇒ bundle + verify ⇒ model.ready
 hibiscus pull <model> --to ~/lelab/models ◀── downloadModel / getModelFile
 source ~/lelab/leLab/.venv/bin/activate
 PORT=/dev/ttyACM0 ./run_on_robot.sh   (lerobot-rollout --policy.path=…/pretrained_model)
```

| # | Who / where | Action | System | API | Copy keys |
|---|---|---|---|---|---|
| 1 | P1 browser, once | Account › Access tokens → Create token, preset "Collection machine", 90 days | Token shown **once** with copy button + CLI hint | `createApiToken` | `account.tokens.preset_collect`, `created_title`, `created_body`, `cli_hint` |
| 2 | P3 machine B | `hibiscus login --server https://robot.example.com`, paste token | CLI calls `getMe`, prints user + workspace + scopes | `getMe` | CLI text (A9) |
| 3 | P3 machine B | Record episodes with LeLab / `lerobot-record` (unchanged) | — | — | — |
| 4 | P3 machine B | `hibiscus push ~/.cache/huggingface/lerobot/<user>/<ds> --name so101_picknplace` | Hashes, uploads parts with progress; on Wi-Fi drop waits and resumes (`getUpload` returns the received `parts`); prints validation progress | `listUploads`, `initUpload`, `uploadPart`, `getUpload`, `completeUpload`, `getDatasetVersion` | `datasets.upload.*`, `datasets.step.*` |
| 5 | Server | Unpack + validate | `pending → unpacking → validating → ready` (or `invalid`) | job `validate_dataset` | `datasets.version_status.*` |
| 6a | P3 machine B | `hibiscus train --dataset so101_picknplace --policy act --preset standard` | Preflight; blockers printed with the same text as UI; run queued as `#42` | `preflightRun`, `createRun` | `training.check.*`, `errors.preflight_failed` |
| 6b | or P2 browser | Dataset detail → "Train on this version" → wizard (F5) | ≤ 5 clicks from file selection to queued | same | `training.*` |
| 7 | Anyone | Watch: browser S-12 or `hibiscus logs -f 42` | Live status/progress/metrics over SSE; heartbeat 15 s | `streamRunEvents` | `runs.*` |
| 8 | Server | Training ends | `running → exporting → succeeded`; model `building → ready`, verified badge | job `export_model` | `models.verified.*`, `notifications.kind.model_ready` |
| 9 | P3 machine B | `hibiscus pull so101_picknplace_act-r42-step100000 --to ~/lelab/models` | Resumable download, sha256 checked against `ETag`/MANIFEST | `getModel`, `downloadModel` or `listModelFiles`+`getModelFile` | `models.download.*` |
| 10 | P3 machine B | `source ~/lelab/leLab/.venv/bin/activate`; `lerobot-find-port`; edit `PORT`/`ROBOT_ID`/camera index; `./run_on_robot.sh` | `lerobot-rollout` drives the follower with the policy for `DURATION` seconds | — (outside Hibiscus) | `models.run_on_robot.*` |
| 11 | P1/P2 | Judge on the robot; if poor, record more episodes → new **version** of the same dataset (step 4 with `--dataset`) → clone run #42 with new version | Version 2 created; clone pre-fills config | `cloneRun` | `training.wizard.cloned_from` |

Failure branches inside F0 (each has its own flow below): token expired/revoked (F10), upload
resume (F4.3), invalid dataset (F4.6), preflight blocker (F5.5), OOM (F6.8), model not verified
(F9.3), serial port wrong (F11).

Click budget (PLAN §6 "upload → train ≤ 5 clicks after choosing the file", browser path):
(1) choose file in S-06 → (2) "Upload" … validation finishes, toast offers **Train on this
version** → (3) click it (wizard opens at step Policy with dataset preselected, ACT recommended)
→ (4) "Next" (preset Standard preselected) → (5) "Start training". Steps Policy→Settings→Review
must therefore have valid defaults so that "Next" never requires input.

---

## F1 — Platform bootstrap (first admin)

1. P1 on the server shell: `python -m app.admin.bootstrap --email <e>` ⇒ prints a one-time link
   (CONTRACT_NOTES §4.2). (Runbook, A8/A2.)
2. → open link ⇒ S-02 Register (no invite banner; email locked) → name, password (≥ 12,
   breach-checked) ⇒ account created.
3. ⇒ **forced 2FA enrolment** S-04 (`auth.mfa_enroll_required.*`) because platform admins must use
   2FA — cannot be skipped, no "later" button.
4. ⇒ Recovery codes S-04b, must tick "I have stored my recovery codes" before continuing.
5. → Administration › Workspaces → Create workspace (name, slug) ⇒ P1 becomes owner
   (`createWorkspace`). Errors: `workspace_slug_taken`, `validation_failed`.
6. → Workspace › Members → Invite (F2).

States: link expired → `errors.one_time_token_invalid` page with "ask the server operator to run
the bootstrap command again".

## F2 — Team: invite, accept, roles, leave

**F2.1 Invite (owner/admin)** S-08
1. → Invite member → email + role (`admin|member|viewer`; owner is not invitable)
   (`createInvite`).
2. If `AuthConfig.email_delivery_enabled` (Cloudflare Email Service live) ⇒ toast
   `workspace.invites.sent`. If **not** ⇒ the response contains `accept_url` ⇒ dialog
   `workspace.invites.link_title/link_body` with a read-only field + Copy button. This is the
   normal path until Cloudflare Email Service is verified on the account (CONTRACT_NOTES §4.1).
3. Pending list shows expiry (72 h); actions Resend (`resendInvite`, old link dies), Revoke.
   Errors: `member_exists`, `quota_exceeded`, `rate_limited`.

**F2.2 Accept — new user** S-02: open link ⇒ `getInvitePreview` ⇒ banner "X invited you to W as
R", email locked → name + password ⇒ `registerWithInvite` (email pre-verified) ⇒ signed in, lands
on workspace overview. If role is admin ⇒ forced 2FA (F3.4) first.
Errors: `invite_invalid` (404 page), `invite_expired` (410 page with "ask to resend"),
`email_taken` (⇒ "sign in instead" button keeping the token), `password_too_weak`,
`password_breached`.

**F2.3 Accept — existing user**: signed in ⇒ S-03 Accept card ⇒ `acceptInvite`. Signed in as a
different email ⇒ `auth.invite.signed_in_as_different_user` with Sign out button
(`invite_email_mismatch`).

**F2.4 Roles**: Members table → role select (`updateMemberRole`). Owner demoting themselves as
last owner ⇒ `last_owner`. Promoting to admin a user without 2FA is allowed; that user is gated
by `mfa_enrollment_required` at next request (copy explains).

**F2.5 Remove / leave**: confirm dialog `workspace.members.remove_confirm` (states that PATs for
this workspace are revoked and data stays) ⇒ `removeMember`. Leaving as last owner ⇒ `last_owner`.

## F3 — Sign-in, recovery and sessions

**F3.1 Sign in** S-01: email + password (+ Turnstile widget when `turnstile_site_key` is set)
⇒ `login`.
* `status=ok` ⇒ redirect to last workspace (or `?next=`).
* `status=mfa_required` ⇒ S-01b code entry ⇒ `loginSecondFactor` (TOTP or recovery code).
* Errors: `invalid_credentials` (generic, no hint which field), `account_locked`
  (`message_retry` with countdown), `account_disabled`, `turnstile_failed` (re-render widget),
  `rate_limited`, `mfa_invalid_code` (keep the field, select its content),
  `mfa_token_invalid` (back to step 1 with `auth.second_factor.expired`).
* Loading: button shows `auth.login.submitting`, disabled; no spinner-only states.

**F3.2 Forgot / reset** S-05: email ⇒ `forgotPassword` ⇒ always the same neutral confirmation
(`auth.forgot.sent`) to avoid account enumeration. When email delivery is disabled show
`auth.forgot.no_email_delivery` **instead** (admin creates a link, F12.3).
Reset link ⇒ new password ⇒ `resetPassword` ⇒ all sessions revoked ⇒ sign-in page with
`auth.reset.done`. Errors: `one_time_token_invalid`, `password_*`.

**F3.3 Verify email**: banner `auth.verify_email.banner` on every page while unverified; actions
that need it fail with `email_not_verified` (dialog with Resend, `resendVerificationEmail`).
Link ⇒ `verifyEmail` ⇒ toast. (Invited users are pre-verified, so mostly the bootstrap admin.)

**F3.4 2FA enrolment** S-04: `setupTotp` ⇒ QR (with text alternative: setup key in monospace,
grouped by 4) → 6-digit code ⇒ `enableTotp` ⇒ 10 recovery codes once (download .txt / copy /
acknowledge checkbox). Disable ⇒ password + code ⇒ `disableTotp`; owners/admins get
`mfa_required_by_role` and the UI hides the button with `account.mfa.required_note`.
Regenerate codes ⇒ re-auth (`mfa_reauth_required`) ⇒ `regenerateRecoveryCodes`.

**F3.5 Sessions** S-09b: list (`listSessions`) with "This device" tag; revoke one / all others.

**F3.6 Silent refresh and forced sign-out**: any 401 `token_expired` from a cookie session ⇒
client calls `refreshSession` once and retries; on `refresh_reuse_detected` ⇒ full-page notice
`errors.refresh_reuse_detected` + sign-in; on `session_revoked` ⇒ sign-in with
`auth.logout.session_ended`. Unsaved form data (wizard) is kept in memory and restored after
re-login when the route is the same.

## F3c — Personal access tokens (for machine B)

S-09: list (name, workspace, scopes, last used, expiry) ⇒ Create dialog: name, workspace,
scope preset (Collection machine = `datasets:write, runs:write, models:read`; Read only =
`datasets:read, runs:read, models:read`) or custom checkboxes, expiry 30/90/365/never (never ⇒
warning text) ⇒ `createApiToken` ⇒ one-time display (`hbp_…`, monospace, Copy) + "I have copied
the token" before the dialog can close. Revoke ⇒ confirm ⇒ `revokeApiToken`.
CLI using a revoked/expired token ⇒ `token_revoked` / `token_expired` text tells exactly where to
create a new one.

## F4 — Datasets

**F4.1 Browser upload** S-06
1. → Upload dataset (from list or empty state) → choose/drop file (single archive; folder ⇒ hint
   to use CLI).
2. Target: new dataset (name) or new version of existing (select). Client checks extension →
   `archive_format_unsupported` early, and size vs `getWorkspaceUsage` upload limit →
   `upload_too_large` early.
3. ⇒ SHA-256 hashing in a Web Worker with progress (`datasets.upload.hashing`); UI stays
   responsive; Cancel available.
4. ⇒ `initUpload` (with `Idempotency-Key`) ⇒ parts PUT sequentially (or 2 in parallel) with
   `X-Content-SHA256`; progress bar (`role=progressbar`, % + part n/N + speed/remaining).
   `upload_part_checksum_mismatch` ⇒ automatic retry ×3 then error.
5. ⇒ `completeUpload` ⇒ "Upload complete, validation started — you can leave" + link to dataset.
   `upload_incomplete` ⇒ resend `missing_parts` automatically, then retry complete.
6. ⇒ Workspace SSE `dataset_version.status` updates the version badge live.

**F4.2 Leave during upload**: `beforeunload` warning while parts are in flight
(`datasets.upload.keep_tab_open`).

**F4.3 Resume**: on return, `listUploads` shows active sessions ⇒ banner
`datasets.upload.resume_prompt` → user re-selects the same file ⇒ client compares size + sha256
(`wrong_file` if different) ⇒ uploads only missing parts (`UploadSession.parts` from `getUpload`).
Offline mid-upload ⇒ `datasets.upload.paused_offline`, resumes on `online` event.
Expired session ⇒ `upload_not_active` ⇒ "Start a new upload".

**F4.4 CLI push** (P3): `hibiscus push <dir|archive> --name <n>` or `--dataset <slug>` for a new
version. The CLI archives a folder as tar (no compression of AV1/parquet), resumes by listing
uploads, prints the validation steps as they finish and exits non-zero on `invalid`, printing
each issue with its episode index and the `datasets.issue.<code>` text (A9 may embed the en/vi
JSON). `hibiscus watch <dir>` pushes each new recording session automatically.

**F4.5 HF import**: S-06 tab "Import from Hugging Face" → `hf://org/repo@rev` ⇒
`importHfDataset` ⇒ job; private repo without stored token ⇒ `hf_token_missing` with link to
Account › Hugging Face token. Bad URI ⇒ `hf_uri_invalid` inline.

**F4.6 Validation report** S-07 tab Validation: 7 steps (`datasets.step.*`) each with status
icon + text, expandable issues table (severity, code text, episode, file, feature). Result:
`passed` / `passed_with_warnings` (green+amber, "Train" enabled, warnings note) / `failed`
(training disabled, primary action "Upload a fixed version"). `failed` version status (infra)
offers **Validate again** (`revalidateDatasetVersion`).
Typical golden-path issues: `video_decode_failed` (truncated AV1 at end of a session) ⇒ copy
tells to delete/re-record that episode; `timestamp_irregular` ⇒ warning only.

**F4.7 Preview / episode viewer** S-07b: thumbnails grid (`getDatasetPreview`), length histogram;
episode page (`getEpisode`): H.264 preview video (CONTRACT_NOTES §4.5) synced with joint plots
(state vs action per joint, toggle per joint, keyboard ←/→ for previous/next episode, space for
play/pause, a cursor line that follows the video time). Held-out episodes of a selected run are
badged. No preview ⇒ `datasets.episode.no_preview`.

**F4.8 Merge**: select ≥ 2 ready versions ⇒ `mergeDatasets` ⇒ new version validated like an
upload; `dataset_schema_mismatch` lists which features differ.

**F4.9 Delete**: dataset/version delete ⇒ confirm; `dataset_in_use` names the blocking run(s) if
the client can resolve them (list runs filtered by dataset).

Empty: no datasets ⇒ S-05 empty card with Upload + CLI snippet; viewer role ⇒
`datasets.list.empty_viewer` (no upload button). Loading: table skeleton rows (not spinners),
`aria-busy` on the table.

## F5 — Training wizard S-10

1. **Dataset**: select dataset + version (only `ready`; others shown disabled with status badge).
   Held-out: slider 0–49 % default 10 % (count shown), or manual episode picker. 0 ⇒ warning.
   No ready dataset ⇒ empty state `training.dataset_step.none_ready_*`.
2. **Policy**: cards from `listPolicies` — name, description, ONNX support, GPU support per GPU,
   badges (LoRA only / needs reward / uses task text / experimental). Cards whose requirements the
   dataset cannot meet are disabled with the reason (`training.policy_step.reason_*`; e.g. TD-MPC
   on the golden dataset: no `next.reward`). ACT carries "Recommended".
3. **Settings**: preset radio (quick / standard / finetune; finetune reveals "Start from" model
   or Hub repo, `requires_init_from`); tabs Basic / Advanced rendered from `getPolicy`
   (`policy_schema`, `train_schema`) with `policy.<type>.<field>.label/help`, default shown,
   "changed" dot, reset-to-default per field; client-side JSON Schema validation inline; run name.
4. **Review**: diff vs defaults, GPU (auto / per GPU with VRAM), priority (> 0 disabled for
   non-admin with `priority_help`), export options (ONNX disabled + reason when `onnx=none`),
   estimate (VRAM bar vs GPU, time, queue ahead, source text; `pending` ⇒ "Measuring…" and
   live update via workspace SSE `estimate.ready`), preflight checklist (`preflightRun` result,
   each check `training.check.<id>` + severity icon + message from `errors.<code>` or
   `training.check_warning.<code>`).
5. **Start** ⇒ `createRun` (Idempotency-Key = wizard instance id, so double-click is harmless)
   ⇒ redirect to S-12 with toast `training.review_step.started`. 422 `preflight_failed` ⇒ stay on
   Review, checklist re-rendered, focus moves to the first failed check. `quota_exceeded` ⇒
   explains which quota with link to Usage. `gpu_insufficient_vram` ⇒ suggestions.
6. **Clone** (`cloneRun`): from run detail ⇒ wizard opens at Review with
   `training.wizard.cloned_from`, back-navigation allowed.

P40 + bf16 selected ⇒ preflight warning `mixed_precision_forced_no` (not an error). Pi0/Pi0.5
without LoRA ⇒ `policy_requires_peft` error with "Use the Fine-tune preset" link.

## F6 — Run detail, live S-12

* Header: `#number name`, status badge (icon + text + colour), progress bar (step/total, ETA),
  GPU, attempt, actions from `allowed_actions` only (never show an action the server will 409).
* Live data: `streamRunEvents` (SSE) with `Last-Event-ID` reconnect, watchdog 45 s; connection
  indicator `common.state.live` / `reconnecting` / `reconnected` (polite live region, not on every
  heartbeat). Fallback polling `getRun` every 10 s if SSE fails 3× in a row.
* **Queued**: position + fair-share explanation (`workspace.queue.fair_share`), link to S-16 queue.
* **Preparing**: "A GPU was assigned. Downloading the dataset…" (no fake progress %).
* **Running**: metrics charts (loss, l1, kld, grad_norm, lr, samples/s, gpu_mem) with the
  permanent honesty note (`runs.metrics.honesty_*`), log tab (follow toggle, search
  `searchRunLogs`, download `getRunLogs`), GPU tab (`getRunTelemetry`).
* **Warnings** (`warning` events) appear as an amber list in Overview, newest first, not toasts
  that disappear: `nan_detected`, `log_silent`, `vram_near_limit`, `mixed_precision_forced_no`,
  `retrying_after_infra_error`, `parser_mismatch`, `heldout_too_small`.
* **Pause** dialog: two radio options with consequences (`runs.action.pause_next_checkpoint_help`
  with step + ETA from `progress.next_checkpoint_step`; `pause_now_help` / `pause_now_no_checkpoint`)
  ⇒ `pauseRun`. Status `pausing` shows "will pause after step N".
* **Resume** ⇒ `resumeRun` ⇒ back to queued (`run_not_resumable` ⇒ suggest Clone).
* **Cancel** ⇒ confirm ⇒ `cancelRun` ⇒ `cancelling` ⇒ `cancelled`.
* **Exporting** ⇒ model card placeholder "Building model…" then link to model.
* **Succeeded** ⇒ summary card: final loss, held-out MAE (with `eval.offline_not_success_rate`),
  model status + verified badge, **Download** and "Run on robot" instructions link.
* **Failed** ⇒ red/neutral card `runs.error.title` + `runs.error.<error_code>` + log excerpt
  (monospace, `lang="en"`, collapsible) + primary action derived from the code: `oom` ⇒ "Copy
  with half batch size" (clone with override `train.batch_size = floor(bs/2)`); `nan_loss` ⇒
  "Copy with lower learning rate"; infra codes ⇒ "Resume" if allowed; `config_invalid` ⇒ "Copy
  and edit settings".
* Auto-retry: `retrying_after_infra_error` warning + status back to queued; attempt counter +1
  and log divider `runs.logs.attempt_divider`.

## F7 — Compare runs S-13

Runs list → select 2–8 checkboxes → "Compare selected (n)" ⇒ `compareRuns` ⇒ overlay chart per
metric (metric selector, log scale, smoothing), legend = run number + name (colour + dash pattern
so lines differ without colour), config diff table ("only differences" default on), held-out eval
table. Different datasets ⇒ `runs.compare.same_dataset_note`. < 2 selected ⇒ button disabled with
`runs.list.compare_limit`. URL holds the run ids so a comparison is shareable within the workspace.

## F8 — Checkpoints, export, offline eval

Run detail › Checkpoints (`listCheckpoints`): step, size, "Latest (used for resume)", "Model
built". Actions: Build model (`exportCheckpoint`) ⇒ job, model appears in S-14; Evaluate
(`evalCheckpoint`) ⇒ job ⇒ Evaluation tab (`getCheckpointEval`): disclaimer block first, overall
MAE/MSE, per-joint table + bar chart, per-episode pred-vs-GT plots (alt text + data table).
No held-out episodes ⇒ `eval.heldout_none`. `checkpoint_not_found` ⇒ refresh list.

## F9 — Models S-14 / S-15

* List (`listModels`): name, policy, run #, step, status, verified badge, ONNX status, size.
  Empty ⇒ `models.list.empty_*`.
* Detail (`getModel`): verification checklist (3 checks, N/A for parity when ONNX unsupported,
  `models.verified.help` explains verified ≠ robot success), ONNX status with reason
  (`policy.onnx_reason.<type>`) or parity detail, eval summary, contents list, model card render
  (`getModelFile MODEL_CARD.md`, rendered as sanitized Markdown), file list (`listModelFiles`).
* **Download** zip (`downloadModel`, browser native download, Range resume by browser) + CLI
  snippet `models.download.cli_command` with Copy.
* **Run on robot** panel (`models.run_on_robot.*`) with the safety note, always visible on ready
  models.
* **Push to Hub** (`pushModelToHub`): repo + private; no token ⇒ `hf_token_missing` with link;
  `hub_repo_invalid` inline; job progress; then `models.hub.pushed`.
* Re-verify (`reverifyModel`), rename (`updateModel`), delete (`deleteModel`, 7-day note).
* `model_not_ready` on download while building ⇒ disabled button with status text instead.
* Parity failed ⇒ badge "Not verified" + `models.onnx_help.failed` (LeRobot folder still usable).

## F10 — Cross-cutting error, empty, loading and offline states

| Situation | Behaviour | Copy |
|---|---|---|
| Any `Problem` | Inline near the action (forms) or toast (background actions) with title + message + request id (copy button) | `errors.<code>.*`, `errors.general.request_id` |
| `validation_failed` | Map `errors[].loc` to fields; summary at top with count + links to fields; focus summary | `errors.general.field_summary_*`, `errors.field.*` |
| 401 `unauthenticated` / `token_expired` | One silent refresh, then sign-in with return URL | `auth.logout.session_ended` |
| 403 `forbidden` / role | Hide actions the role cannot do; direct navigation ⇒ S-00 forbidden page | `common.error_page.forbidden_*` |
| 403 `csrf_failed` | Fetch new CSRF cookie by a GET, retry once, then show message | `errors.csrf_failed` |
| 404 `not_found` | Full-page not-found that also covers "not a member" (no existence oracle) | `common.error_page.not_found_*` |
| 409 state conflicts | Re-fetch the resource, re-render actions, show message | `errors.conflict`, `errors.run_invalid_transition` |
| 429 | Disable the button for `retry_after_s` with countdown | `errors.rate_limited.message_retry` |
| 5xx / network | Toast with Retry; queries auto-retry 2× with backoff; page-level error boundary shows `crash_*` | `errors.internal_error`, `errors.general.network` |
| Offline (`navigator.onLine=false`) | Top banner; uploads pause; SSE indicator "reconnecting" | `common.state.offline` |
| Unknown code | Fallback title/message + request id | `errors.general.fallback_*` |
| Loading | Skeletons for lists/cards (≥ 300 ms delay before showing to avoid flicker); buttons show verb-ing text; never block the whole page except the initial auth check | `common.state.loading*` |
| Empty | Every list has an empty state with the next action (and a role-aware variant) | `*.empty_*` |

## F11 — Run the bundle on the robot (outside Hibiscus)

Documented in the user guide (`docs/user-guide/vi/06-chay-tren-robot.md`), summarised in the
model page. Inside the LeLab venv (LeLab has no inference; we use LeRobot's CLI that LeLab
already installs): unzip → `source ~/lelab/leLab/.venv/bin/activate` → `lerobot-find-port` →
set `PORT`, `ROBOT_ID` (must match calibration), camera index → `./run_on_robot.sh` (runs
`lerobot-rollout --policy.path=<bundle>/pretrained_model …` for `DURATION` s, default 60).
Error branches: wrong port (`could not open port`), calibration id mismatch (LeRobot prompts to
calibrate), camera index wrong (OpenCV fails to open), policy expects a camera key the robot
config does not provide (rename in script must match dataset camera key, e.g. `wrist_cam`).

## F12 — Platform administration S-17

* Users (`adminListUsers`, `adminUpdateUser`): enable/disable, unlock, grant/revoke platform
  admin (requires target 2FA ⇒ explained), reset 2FA (account recovery, strong confirm), revoke
  sessions + PATs (`adminRevokeUserSessions`).
* **Reset link** (`adminCreatePasswordResetLink`): used when email is off ⇒ dialog with link +
  copy + "audited" note.
* Audit log (`adminListAuditEvents`): filters action/user/date, outcome badges, localised action
  names `admin.audit.action.*`.
* System (`adminGetSystem`): versions, storage per bucket + disk free, queue depth, worker
  heartbeats (stale ⇒ amber), **email provider** (`cloudflare` = Cloudflare Email Service is the
  production choice; `none` ⇒ hint about copy-link flows).
* Entry requires 2FA; if Cloudflare Access is enabled for `/admin*` the user passes Access first
  (outside the SPA).

## F13 — Quotas, GPUs, queue

* Admin › Quotas (`adminListQuotas`, `adminUpsertQuota`): workspace default + per-user overrides
  (concurrent runs, queued runs, GPU-h/month, storage, max upload). Defaults per CONTRACT_NOTES
  §4.8 (1 concurrent run/user, 200 GPU-h/month, 200 GiB/workspace, 50 GiB/upload).
* Admin › GPUs (`adminUpdateGpu`): drain / disable (confirm explains re-queue) / enable.
* Everyone: Queue S-16 (`getQueue`, `listGpus`): order, anonymised foreign runs, GPU cards with
  util/VRAM/temp/power; P40 card notes "no bf16".
* Workspace › Usage (`getWorkspaceUsage`): meters with numbers (not colour only), near-limit text.

## F14 — Notifications

* Bell with unread count (`listNotifications`, live via `streamWorkspaceEvents` `notification`),
  panel with `notifications.kind.*`, link to target, mark read / all read.
* Account › Notification channels (`createNotificationChannel`, `testNotificationChannel`):
  email (via the configured provider — Cloudflare Email Service in production), Discord,
  Telegram, webhook; event checkboxes.
* Workspace settings `notify_on` for workspace-wide notifications.

## F15 — Account settings

Profile (name, language — switching language re-renders immediately and persists via
`updateMe`), password change (`changePassword`, other sessions revoked), 2FA, sessions, tokens,
Hugging Face token (`setHfToken` / `deleteHfToken`; never displayed back, only "stored on …").
