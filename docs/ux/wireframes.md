# Low-fidelity wireframes

ASCII wireframes for every screen A6 builds. They fix **content, hierarchy and states**, not
visual design (A6 uses shadcn/ui + Tailwind, ADR-0007). Labels are English shorthand for the
i18n keys noted beside them; Vietnamese strings are usually 10–30 % longer — layouts must wrap,
never truncate primary actions. Breakpoints: `≥ 1024px` desktop (sidebar), `640–1023px` tablet
(collapsible sidebar), `< 640px` phone (top bar + drawer; tables become stacked cards).

Legend: `[Button]` primary/secondary button · `( ) / (•)` radio · `[x] / [ ]` checkbox ·
`[▾ …]` select · `[____]` input · `▓▓░░` progress · `⟳` live/refresh · `⚠` warning · `✖` error
· `✔` ok · `…` truncated content · `{key}` i18n key.

Screen index: S-00 shell & system pages · S-01 sign in · S-01b second factor · S-02 register
from invite · S-03 accept invite · S-04 2FA enrol + S-04b recovery codes · S-05 forgot/reset ·
S-08 members & invites · S-09 access tokens · S-09b security/sessions · S-11 overview ·
S-05d datasets list · S-06 upload · S-07 dataset detail/validation · S-07b episode viewer ·
S-10 training wizard (4 steps) · S-12 run detail live · S-12b pause dialog · S-13 compare ·
S-14 models list · S-15 model detail · S-16 queue & GPUs · S-17 admin · S-18 notifications.

---

## S-00 App shell, not-found, forbidden, crash

```
┌────────────────────────────────────────────────────────────────────────────────┐
│ [Skip to main content]  (visible on focus)                     {common.app.*}  │
│ Hibiscus  [▾ Lab SO-101 · Owner]           🔔3   [▾ vi/en]  [▾ Khoa]           │
├───────────────┬────────────────────────────────────────────────────────────────┤
│ Overview      │ Breadcrumb: Lab SO-101 › Runs › #42                            │
│ Datasets      │                                                                │
│ Runs          │  <main id="main">  page content                                │
│  + New run    │                                                                │
│ Compare       │                                                                │
│ Models        │                                                                │
│ GPU queue     │                                                                │
│ ─────────     │                                                                │
│ Members       │                                                                │
│ Settings      │                                                                │
│ Usage         │                                                                │
│ ─────────     │                                                                │
│ Admin (P1)    │                                                                │
│ User guide ↗  │                                                                │
└───────────────┴────────────────────────────────────────────────────────────────┘
Banners (stacked above <main>, each dismissible only if non-critical):
 ⚠ Your email is not verified … [Send again]                {auth.verify_email.banner}
 ⚠ You are offline …                                         {common.state.offline}

Not found (also: not a member — same page, no oracle)        {common.error_page.not_found_*}
┌──────────────────────────────────────┐
│  Page not found                      │
│  The page does not exist, or …       │
│  [Go to overview]                    │
└──────────────────────────────────────┘
Crash boundary: title + body + "Request ID: 4f3c… [Copy]" + [Reload page]
Phone: top bar = ☰ · Hibiscus · 🔔 · avatar; sidebar becomes a drawer (focus-trapped).
```

## S-01 Sign in / S-01b second factor

```
┌──────────────────────────────────────────┐   ┌──────────────────────────────────────────┐
│ Hibiscus                       [▾ vi/en]  │   │ Two-factor authentication                │
│ Sign in to Hibiscus     {auth.login.title}│   │ Enter the 6-digit code from your app.    │
│                                          │   │ Authentication code                      │
│ Email     [_____________________]        │   │ [ _ _ _ _ _ _ ]  autocomplete=one-time-code│
│ Password  [_____________________] [👁]   │   │ ✖ The code is wrong or expired … (inline)│
│ ┌ Security check (Turnstile) ┐           │   │ [Verify]                                 │
│ └────────────────────────────┘           │   │ Use a recovery code instead              │
│ ✖ Wrong email or password … (alert)      │   └──────────────────────────────────────────┘
│ [Sign in]                                │   Recovery mode: single text field
│ Forgot your password?                    │   "xxxx-xxxx" + help {auth.second_factor.recovery_help}
│ Accounts are created by invitation only. │
└──────────────────────────────────────────┘
States: submitting (button text "Signing in…", disabled) · locked (message_retry countdown,
button disabled) · Turnstile failed (widget re-rendered + message). No "register" link.
```

## S-02 Register from invite · S-03 accept invite (signed in)

```
┌───────────────────────────────────────────────────────────┐
│ Create your account                                       │
│ ℹ Khoa invited you to the workspace Lab SO-101 as Member. │
│ Email      linh@lab.vn  (locked)   {auth.register.email_locked}
│ Your name  [______________]                               │
│ Password   [______________]  ▓▓▓░ Strong                  │
│            At least 12 characters …                       │
│ Repeat     [______________]                               │
│ Language   (•) Tiếng Việt  ( ) English                    │
│ [Create account and join]                                 │
└───────────────────────────────────────────────────────────┘
Checking state: "Checking your invite…" skeleton. Invalid / expired: full card with title
{auth.invite.invalid_title | expired_title}, message from errors.*, no form.
S-03: card "Join Lab SO-101 — You are signed in as linh@… Accept to join as Member."
      [Accept invite] [Cancel]; mismatch ⇒ {auth.invite.signed_in_as_different_user} [Sign out]
```

## S-04 2FA enrolment · S-04b recovery codes

```
┌──────────────────────────────────────────────────────────────┐
│ Set up two-factor authentication                             │
│ (forced variant shows {auth.mfa_enroll_required.body})       │
│ 1. Scan this QR code …                                       │
│    ┌────────┐   Can't scan? Enter this setup key manually:   │
│    │ ▚▞▚▞▚▞ │   JBSW Y3DP EHPK 3PXP  [Copy]                   │
│    └────────┘                                                │
│ 2. Enter the 6-digit code …   [ _ _ _ _ _ _ ]  [Turn on]     │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│ Recovery codes                                               │
│ If you lose your phone … They will not be shown again.       │
│  1. ab12-cd34   6. …        (monospace list, <ol>)           │
│ [Download as .txt] [Copy all codes]                          │
│ [ ] I have stored my recovery codes                          │
│ [Continue]  (disabled until checked)                         │
└──────────────────────────────────────────────────────────────┘
```

## S-05 Forgot / reset password

```
Forgot:  title · body · Email [_____] · Turnstile · [Send reset link]
  ⇒ success panel (same text whether or not the account exists) {auth.forgot.sent}
  ⇒ email disabled: info panel {auth.forgot.no_email_delivery} instead of the form result
Reset:   New password [____] (strength) · Repeat [____] · [Set new password]
  ⇒ token invalid: errors.one_time_token_invalid card + [Request a new link]
```

## S-11 Workspace overview

```
┌ Hello, Linh ─────────────────────────────────────────────────────────────────┐
│ [Upload a dataset]  [Start training]                                         │
├ Active runs ────────────────────────┬ GPUs ──────────────────────────────────┤
│ #42 picknplace ACT  Running ▓▓▓░ 61%│ cuda0 RTX 3060 12GB  Running #42       │
│     step 61 000/100 000 · ETA 1h12m │   util 97% · 1.8/12 GB · 66°C          │
│ #43 smolvla test    Queued (2nd)    │ cuda1 Tesla P40 24GB  Idle             │
├ Recent datasets ────────────────────┤   No bf16: fp32 only                   │
│ so101_picknplace v2  Ready · 20 ep  ├ Recent models ─────────────────────────┤
│ ...                                 │ so101_picknplace_act-r41-step10000 ✔   │
└─────────────────────────────────────┴────────────────────────────────────────┘
Empty workspace: "Get started in three steps" card (upload → train → download) with the
CLI snippet; no empty widgets. No workspace at all: {workspace.none.*} full-page card.
```

## S-08 Members & invites

```
Members                                                          [Invite member]
┌───────────────┬──────────────────┬───────────┬────────┬──────────┬───────────┐
│ Name          │ Email            │ Role      │ 2FA    │ Joined   │ Actions   │
├───────────────┼──────────────────┼───────────┼────────┼──────────┼───────────┤
│ Khoa (you)    │ khoa@…           │ Owner     │ ✔ On   │ 15/11    │ [Leave]   │
│ Linh          │ linh@…           │ [▾Member] │ ✖ Off  │ 16/11    │ [Remove]  │
└───────────────┴──────────────────┴───────────┴────────┴──────────┴───────────┘
Pending invites
│ tuan@…  Member  Expires 18/11 09:30   [Resend] [Revoke]                      │
Invite dialog: Email [____] Role [▾ Member] (role help text under select) [Send invite]
  ⇒ email on: toast {workspace.invites.sent}
  ⇒ email off: dialog "Share this invite link" [https://robot…/invite/…] [Copy] + note
Viewer/member: table read-only, no Invite button, no Pending section.
Phone: each member is a card: name, email, role badge, actions in a "⋯" menu.
```

## S-09 Access tokens (PAT) · S-09b security & sessions

```
Personal access tokens                                             [Create token]
Tokens let the hibiscus CLI on a collection machine act for you …
│ collect-pc-lab2  Lab SO-101  Upload datasets, Start runs, Download models     │
│   Last used 2 hours ago from 192.168.1.20 · Expires 13/02/2027   [Revoke]     │
Create dialog:
  Token name [collect-pc-lab2]   Workspace [▾ Lab SO-101]
  Permissions (•) Collection machine  ( ) Read only  ( ) Custom: [x] … (5 scopes)
  Expires after [▾ 90 days]  (No expiry ⇒ ⚠ not recommended)
  [Create token]
One-time display (modal, cannot close by Esc/outside click until acknowledged):
  Copy your token now · hbp_3Hk…9Qa  [Copy]
  On the collection machine run: hibiscus login --server https://robot.example.com
  [ ] I have copied the token   [Done]
Empty: {account.tokens.empty_title/body} + [Create token]

Security page: Password [Change password] · Two-factor ✔ On (Required for your role) ·
Recovery codes "8 unused codes left" [Create new recovery codes] ·
Active sessions table (device, IP, last active, "This device") [Sign out] · [Sign out all other devices]
Hugging Face token: "A token is stored (set 12/11)" [Replace token] [Remove token]
Notification channels: list + [Add channel] + [Send test message]
```

## S-05d Datasets list

```
Datasets                         [Import from Hugging Face] [Merge] [Upload dataset]
[Search ____]
┌──────────────────────┬──────────┬──────────┬───────────────────┬──────────────┐
│ Name                 │ Latest   │ Episodes │ Status            │ Updated      │
├──────────────────────┼──────────┼──────────┼───────────────────┼──────────────┤
│ so101_picknplace     │ v2       │ 20       │ ✔ Ready           │ 2 hours ago  │
│ so101_stack          │ v1       │ 35       │ ⟳ Validating      │ just now     │
│ old_session          │ v1       │ —        │ ✖ Invalid         │ 3 days ago   │
└──────────────────────┴──────────┴──────────┴───────────────────┴──────────────┘
Empty: illustration-free card, {datasets.list.empty_title/body}, [Upload dataset],
  code block: hibiscus push <folder> --name <dataset name>  [Copy]
Loading: 5 skeleton rows, table aria-busy="true".
```

## S-06 Upload (browser)

```
Upload a dataset
┌ Drop an archive here or choose a file ─────────────────────────────────────────┐
│                         [Choose file]                                          │
│  Accepted: .zip, .tar, .tar.gz, .tar.zst, .rar (RAR5) …                        │
│  Uploading a folder? Use the CLI: hibiscus push <folder> --name …   [Copy]      │
└────────────────────────────────────────────────────────────────────────────────┘
Add to (•) New dataset  Name [so101_picknplace]   ( ) New version of [▾ …]
Largest allowed upload: 50 GiB
[Upload]
── in progress ─────────────────────────────────────────────────────────────────
Picknplace_20261114_221710.rar · 1.9 GiB
Checking file integrity… ▓▓▓▓▓░░░░ 54%     (hash step)
Uploading part 12 of 31  ▓▓▓▓░░░░░ 38%  · 8.2 MiB/s · 2 min left   [Cancel upload]
⚠ Keep this tab open until the upload finishes …
⚠ Connection lost. The upload pauses and resumes automatically …      (offline)
── done ────────────────────────────────────────────────────────────────────────
✔ Upload complete. Unpacking and validation started — you can leave this page.
  [Open dataset]
Resume banner (on page load if listUploads has an active session):
  ⚠ An unfinished upload of X was found. Choose the same file …  [Resume upload] [Cancel upload]
Tabs at top: [Upload file] [Import from Hugging Face] — HF tab: hf://… [____] help [Import]
```

## S-07 Dataset detail · validation

```
so101_picknplace                                   [Train on this version] [⋯]
Version [▾ v2 · Ready · 15/11 21:17]        Tabs: Overview | Validation | Episodes
── Overview ─────────────────────────────────────────────────────────────────────
Source Uploaded · LeRobot format v3.0 · Robot type so_follower · 30 fps
Cameras observation.images.wrist_cam (640×360, AV1)
Joints shoulder_pan.pos, shoulder_lift.pos, elbow_flex.pos, wrist_flex.pos, wrist_roll.pos, gripper.pos
State size 6 · Action size 6 · Tasks "pick and place" · 20 episodes · 11 277 frames
Content fingerprint 3fa9…c1  [Copy]
ℹ Versions never change after upload …
── Validation ───────────────────────────────────────────────────────────────────
⚠ Passed with warnings · 0 errors · 1 warning   [Validate again]
✔ File integrity        The uploaded bytes match …
✔ Unpack archive
✔ Folder structure
✔ Features and joints
✔ Video decoding
⚠ Timestamps            ▸ 1 warning
   │ Warning │ Timestamps are not evenly spaced … │ Episode 7 │ data/…parquet │ —   │
   │ ▸ Technical detail (English, lang="en")                                       │
✔ Statistics
ℹ Warnings do not block training, but read them …
Failed variant: header "✖ Validation failed", primary action becomes [Upload a fixed version],
"Train on this version" disabled with tooltip {errors.dataset_version_not_ready.message}.
Running variant: steps show ⟳ / Not started; live via workspace SSE.
```

## S-07b Episode viewer

```
Episode 7 / 19            [◀ Previous episode] [Next episode ▶]   (← / → keys)
Task: pick and place · 563 frames · 18.8 s          Camera [▾ wrist_cam]
┌──────────────────────────────┐  Joint positions over time
│                              │  [x] shoulder_pan [x] shoulder_lift [x] elbow_flex
│        video 640×360         │  [x] wrist_flex   [x] wrist_roll    [x] gripper
│    (H.264 preview, ≤480p)    │  ┌──────────────────────────────────────────────┐
│ ▶ ━━━━━━●━━━━━ 07.2 / 18.8 s │  │ ~~~~~~╲___/~~~~  │ (cursor follows video)    │
└──────────────────────────────┘  │ state ── solid   action ┄┄ dashed            │
ℹ Playing a reduced-quality preview …  └──────────────────────────────────────────────┘
                                   [Show data as table]
Thumbnails grid (Episodes tab): 4–6 per row, each "Ep 7 · 18.8 s", badge "Held out"
when a run is selected; length distribution histogram with table alternative.
```

## S-10 Training wizard (4 steps)

```
New training run                     Step 2 of 4: Policy      ① Dataset ─ ② Policy ─ ③ Settings ─ ④ Review
── ① Dataset ────────────────────────────────────────────────────────────────────
Dataset [▾ so101_picknplace]  Version [▾ v2 · Ready]   20 episodes · 30 fps · cameras: wrist_cam
Episodes held out for evaluation: ━━●━━━━━━ 10% (2 episodes)  [Choose episodes manually]
                                                                     [Next]
── ② Policy ─────────────────────────────────────────────────────────────────────
┌ ACT  ★ Recommended ──────────┐ ┌ Diffusion Policy ──────────┐ ┌ VQ-BeT ───────────────┐
│ Action Chunking Transformer… │ │ Generates actions by …     │ │ Discretises …         │
│ ONNX: export included        │ │ ONNX: encoder + denoiser   │ │ ONNX: may come in 1.1 │
│ RTX 3060 ✔  Tesla P40 ✔      │ │ RTX 3060 ✔  Tesla P40 ✔    │ │ …                     │
└──────────────────────────────┘ └────────────────────────────┘ └───────────────────────┘
┌ TD-MPC (disabled) ───────────┐ ┌ SmolVLA ───────────────────┐ ┌ Pi0  Experimental ────┐
│ Not available for this       │ │ Uses task text             │ │ LoRA only · P40 only  │
│ dataset: no reward signal    │ │ 3060 limited · P40 ✔       │ │ RTX 3060 ✖ P40 limited│
└──────────────────────────────┘ └────────────────────────────┘ └───────────────────────┘
(cards are a radiogroup: arrow keys move, Space selects)          [Back] [Next]
── ③ Settings ───────────────────────────────────────────────────────────────────
Preset (•) Quick (10k)  ( ) Standard (100k)  ( ) Fine-tune from a checkpoint
       A short run to check that data and settings work …
Run name [picknplace ACT bs8]
Tabs: [Basic] [Advanced]
 Training steps        [ 10000 ]   Default: 100000 · ● changed  [Reset to default]
 Batch size            [ 8 ]       Samples per step … If out-of-memory, halve this.
 Checkpoint every N    [ 5000 ]
 Mixed precision       [▾ bf16 (RTX 3060 only)]
 Image augmentation    [ ] 
 Action chunk size     [ 100 ]     How many future actions …
 Actions per prediction[ 100 ]     ✖ Must not exceed the chunk size (inline)
 …
Advanced tab: ⚠ "These settings are passed straight to lerobot-train …"; same field pattern,
shows "LeRobot flag: --policy.dim_model" under each field.
                                                                  [Back] [Next]
── ④ Review and start ───────────────────────────────────────────────────────────
Summary  ACT · so101_picknplace v2 · Quick · 2 held-out episodes · seed 1000
Settings changed from defaults:  steps 100000 → 10000 · save_freq 10000 → 5000
GPU [▾ Automatic]   Priority [ 0 ] (higher needs admin)
Model bundle [x] Export ONNX and check parity  [ ] fp16  [x] Offline evaluation  Name [auto]
Estimate  GPU memory ▓▓░░░░░░░░ about 1.8 GB of 12 GB · Training time about 20 min ·
          Queue: 1 run ahead · Measured by a 20-step trial run on the GPU.
Pre-start checks
 ✔ Dataset version is validated        ✔ Settings are valid for this policy
 ✔ Dataset cameras match …             ⚠ Precision is supported by the GPU — P40 forces fp32
 ✖ Within your quota — Quota reached: …                                   (focus here on 422)
                                                              [Back] [Start training]
```

## S-12 Run detail (live) · S-12b pause dialog

```
Run #42 · picknplace ACT bs8      ● Running on RTX 3060      ⟳ Live
Step 61 000 of 100 000 ▓▓▓▓▓▓░░░░ 61% · ETA 1h 12m · Attempt 1 · Next checkpoint at step 70 000
[Pause] [Cancel run] [Copy settings to a new run] [⋯ Download full log]
Tabs: Overview | Metrics | Log | Checkpoints | Evaluation | Events | Settings | GPU
── Overview ──────────────────────────────────────────────────────────────────────
⚠ GPU memory use is above 95% …                      (warnings list, newest first)
Dataset so101_picknplace v2 · Policy ACT · Preset Quick · Seed 1000 · Held-out 3, 17
Latest: loss 0.166 · l1 0.113 · kld 0.005 · grad norm 16.0 · lr 1e-5 · 73 samples/s · 1.78 GB
── Metrics ───────────────────────────────────────────────────────────────────────
┌ ℹ How to read these numbers ─────────────────────────────────────────────────────┐
│ Training loss shows how well the model fits the training data … does not mean   │
│ the robot will succeed …                                   (not dismissible)    │
└──────────────────────────────────────────────────────────────────────────────────┘
[▾ Training loss] [x] Logarithmic scale  Smoothing ━━●━━   [Show data as table]
┌──────────────────────────────────────────────────────────────────────────────┐
│7 ╲                                                                           │
│   ╲__                                                                        │
│      ‾‾‾───────────────────────────────── 0.166                              │
└─────────────────────────────────── step ─────────────────────────────────────┘
Small multiples: L1 loss · KL loss · Gradient norm · Learning rate · Throughput · Peak GPU memory
── Log ──────────────────────────────────────────────────────────────────────────
[Search the log ____] 3 matches   [x] Follow new lines   [Download full log (.log)]
│ INFO 2026-11-14 23:12:52 ot_train.py:894 step:10K smpl:78K … loss:0.166 … │ (monospace, lang=en)
── Failed variant (replaces Overview top) ────────────────────────────────────────
✖ Why the run failed
  The GPU ran out of memory. Copy this run and halve the batch size, or choose …
  [Copy with half batch size] [Resume] (if allowed)
  ▸ Last log lines (50, monospace)
── Succeeded variant ─────────────────────────────────────────────────────────────
✔ Training finished · final loss 0.165 · held-out MAE 1.92
  ℹ These numbers … are not the robot's success rate …
  Model so101_picknplace_act-r42-step10000 · ✔ Verified · ONNX passed   [Download] [Run on robot ▸]

S-12b Pause run #42
 (•) At the next checkpoint (recommended)
     Keeps training until step 70 000 (about 16 min), saves a checkpoint, then frees the GPU.
 ( ) Immediately
     Stops now. Progress since the last checkpoint (step 60 000) is lost.
                                                           [Cancel] [Pause]
Queued variant: "Waiting for a free GPU. Position 2 in the queue." + fair-share note + link.
Pausing variant: badge "Pausing" + "Will pause after the next checkpoint at step 70 000".
```

## S-13 Compare runs

```
Compare runs   Runs: [#41 ✕] [#42 ✕] [#45 ✕] [+ add]        Metric [▾ Training loss] [x] log
┌──────────────────────────────────────────────────────────────────────────────┐
│ ── #41 ACT bs8 (solid)   ┄┄ #42 ACT bs16 (dashed)   ·· #45 Diffusion (dotted)│
│ overlay chart                                                                │
└──────────────────────────────────────────────────────────────────────────────┘
ℹ Runs use different datasets: their losses are not directly comparable. (when applicable)
Settings that differ   [x] Show only differences
│ setting              │ #41      │ #42      │ #45       │
│ policy               │ act      │ act      │ diffusion │
│ train.batch_size     │ 8        │ 16       │ 32        │
Held-out evaluation    │ MAE      │ 1.92     │ 1.75     │ 2.40      │
Empty: "Select at least two runs from the run list to compare them." [Go to runs]
```

## S-14 Models list · S-15 model detail

```
Models
│ Name                                │ Policy │ Run │ Step   │ Status │ Verified │ ONNX     │ Size  │
│ so101_picknplace_act-r42-step10000  │ ACT    │ #42 │ 10 000 │ Ready  │ ✔        │ Passed   │ 210MB │
│ so101_picknplace_smolvla-r43-…      │ SmolVLA│ #43 │ 20 000 │ Ready  │ ✔        │ Not avail│ 1.9GB │
│ …-r44-step5000                      │ ACT    │ #44 │ 5 000  │ ⟳ Building │ —    │ Exporting│ —     │

Model so101_picknplace_act-r42-step10000                       [Download] [⋯ Push to Hub · Rename · Delete]
From run #42, step 10 000 · Trained on so101_picknplace v2
┌ ✔ Verified ───────────────────────────────────────────────────────────────────┐
│ ✔ Loads in LeRobot and predicts a valid action                                │
│ ✔ Every file matches its fingerprint in MANIFEST.json                         │
│ ✔ ONNX output matches PyTorch  (largest difference 3.1e-6, allowed 1e-4)      │
│ ℹ Verified … does not mean the robot will succeed at the task.  [Run checks again]
└───────────────────────────────────────────────────────────────────────────────┘
Download   [Download bundle (.zip, 210 MiB)]  Large downloads can be resumed …
           Or on the robot computer:  hibiscus pull so101_…-r42-step10000 --to ~/lelab/models [Copy]
Run it on the robot   (ordered list, each command in a copyable code block)
  1 Unzip … 2 source ~/lelab/leLab/.venv/bin/activate 3 lerobot-find-port
  4 Set PORT, ROBOT_ID … 5 PORT=/dev/ttyACM0 ./run_on_robot.sh
  ⚠ Keep a hand near the power switch the first time …
Offline evaluation (with disclaimer first) · What is inside (7 items) · Model card (rendered) · Files
ONNX not supported variant: "No ONNX export in this version — SmolVLA contains a language model …"
Parity failed variant: "Not verified" badge, ✖ ONNX output differs … LeRobot folder is still fine.
```

## S-16 GPU queue

```
GPU queue
┌ cuda0 · RTX 3060 12 GB · Online ───────┐ ┌ cuda1 · Tesla P40 24 GB · Online ─────┐
│ Running #42 (Linh) · util 97%          │ │ Busy (another workspace)               │
│ Memory 1.8 / 12 GB ▓░░░ · 66 °C · 150 W│ │ No bf16: runs on this GPU use fp32     │
└────────────────────────────────────────┘ └────────────────────────────────────────┘
ℹ Order uses fair-share: members who used less GPU time recently go first.
│ Position │ Run                      │ Started by │ GPU   │ Waiting since │ Est. start │
│ 1        │ Run from another workspace│ —         │ auto  │ 10:02         │ 10:40      │
│ 2        │ #43 smolvla test         │ Linh       │ cuda1 │ 10:05         │ —          │
Empty: {workspace.queue.empty}
```

## S-17 Administration

```
Administration    Tabs: Users | Workspaces | Quotas | GPUs | Audit log | System
(entry gate: if no 2FA ⇒ {admin.mfa_gate} with [Set up two-factor authentication])
── Users ────────────────────────────────────────────────────────────────────────
│ Email     │ Name │ Status   │ 2FA │ Last sign-in │ Actions ⋯                    │
│ linh@…    │ Linh │ Active   │ Off │ 2 h ago      │ Disable · Unlock · Reset 2FA │
│           │      │          │     │              │ Make platform admin (needs 2FA)
│           │      │          │     │              │ Create password reset link   │
Reset link dialog: link field [Copy] + "Send this link … recorded in the audit log."
── Quotas ───────────────────────────────────────────────────────────────────────
Workspace default: Concurrent runs [1] Queued runs [3] GPU-h/month [200] Storage GiB [200] Upload GiB [50] [Save]
User overrides: + Add user override
── GPUs ─────────────────────────────────────────────────────────────────────────
cuda0 Online  [Drain] [Disable]     cuda1 Draining  [Enable]
── Audit log ────────────────────────────────────────────────────────────────────
Filters: Action [▾] User [▾] From/To
│ 15/11 09:30 │ Khoa │ Created access token │ collect-pc-lab2 │ 1.2.3.4 │ Success │
── System ───────────────────────────────────────────────────────────────────────
Hibiscus 0.1.0 · LeRobot 0.7.1 · API 0.1.0 · Runs waiting 2 · Disk free 312 GiB
Workers: gpu-0 heartbeat 3 s ago ✔ · gpu-1 ⚠ no heartbeat for 2 min
Email delivery: Cloudflare Email Service ✔ enabled   (or: Off — … + hint)
```

## S-18 Notifications panel

```
🔔 (button, aria-label "Open notifications, 3 unread")
┌ Notifications ───────────────────── [Mark all as read] ┐
│ ● Run #42 "picknplace ACT" finished successfully. 5 min │
│ ● Dataset so101_stack v1 failed validation …     1 h    │
│   Model so101_…-r41 is ready to download.        1 d    │
└─────────────────────────────────────────────────────────┘
Empty: {notifications.empty}
```
