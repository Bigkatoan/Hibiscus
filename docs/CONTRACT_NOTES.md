# Contract notes — v0.1 (frozen 2026-11-15)

Owner: A1. This file records (1) the contract inventory, (2) every place the contract deviates
from or refines `docs/PLAN.md` and why, (3) deployment facts that bind A8/A2/A4, (4) open
questions for the user, (5) the change-request log. Decisions in PLAN §10 and ADR-1..11 are
final and were not reopened.

## 1. Contract inventory (frozen)

| Artifact | Path | Verified by |
|---|---|---|
| OpenAPI 3.1 (99 paths, 120 operations, 152 schemas) | `api/openapi.yaml` | `openapi-spec-validator` (VALID) |
| Policy / train JSON Schemas (LeRobot 0.7.1) | `api/policy-schemas/*.json` + generator `backend/app/runs/policy_schema.py` | `--check`, `backend/tests/contract` |
| Presets | `api/policy-schemas/presets.json` | validated vs schemas for all 7 policies × 3 presets |
| Bundle JSON Schemas | `api/bundle-schemas/*.schema.json` | examples from the real ACT checkpoint validate |
| DB models (27 tables) | `backend/app/db/models.py`, `docs/db-schema.md` | imports, mappers configure, PG DDL compiles, names unique, mypy --strict |
| Run lifecycle | `docs/spec/run-lifecycle.md` | review |
| Log parsing | `docs/spec/log-parsing.md`, `worker/train/log_patterns.py` | 17 pytest cases incl. real log fixture |
| Bundle | `docs/spec/bundle.md` | schema tests |
| Policy schema | `docs/spec/policy-schema.md` | generator run |
| ADRs | `docs/adr/0001..0011` | — |
| Ownership / contributing | `docs/OWNERSHIP.md`, `docs/CONTRIBUTING.md` | — |

## 2. Deviations / refinements vs PLAN.md

* **D1 Upload transport.** PLAN ADR-4 says "S3 multipart presigned upload"; ADR-10 (also PLAN)
  requires chunks through the API because MinIO is not public. Contract: `POST /uploads` →
  `PUT /uploads/{id}/parts/{n}` (raw body ≤ 64 MiB, `X-Content-SHA256`) → `POST /complete` |
  `DELETE`. The API streams each part into an S3 multipart part; no presigned URL is ever issued.
* **D2 Pause semantics.** PLAN: "pause = save a checkpoint then stop". `lerobot-train` is run
  unmodified (ADR-3) and has no "checkpoint now" signal, so `POST /runs/{id}/pause` takes
  `mode=next_checkpoint` (default; keeps training until the next `save_freq` checkpoint, then
  stops, no progress lost) or `mode=now` (stop immediately, resume from the last checkpoint).
  UI shows the step/ETA of the next checkpoint. (Alternative rejected: monkey-patching lerobot's
  `should_save_checkpoint` from a launcher — violates ADR-3's "unmodified".)
* **D3 Export failure does not fail the run.** PLAN draws `exporting → succeeded | failed`. A bug
  or parity failure in export leaves the run `succeeded` with model `failed` / not verified (the
  training result is valid and re-export is possible); `exporting → failed` is only for infra
  failures after the retry budget.
* **D4 Bundle name** `<model_name>-r<run_number>-step<N>` instead of `<model_name>-<run_id>-step<N>`
  (UUIDs make unreadable folder names; run number is unique per workspace and MANIFEST.json
  carries the full run id).
* **D5 Schemas generated at build time.** ADR-5 says the API "reads config dataclasses directly";
  to keep torch/LeRobot out of the API image, the generator runs in an environment with the
  pinned LeRobot and the API serves the committed JSON. Same source, same result, CI `--check`.
* **D6 PAT scopes.** PLAN lists `datasets:write, runs:read, models:read`; contract adds
  `datasets:read` and `runs:write` (needed by `hibiscus train` and read-only collect machines).
  `datasets:write ⇒ datasets:read`, `runs:write ⇒ runs:read`.
* **D7 LeLab.** PLAN §8.2 (A9 "nhánh hibiscus-integration của LeLab") and M6 ("patch LeLab") are
  superseded by ADR-11 / PLAN §10.5: A9 owns only `cli/`; integration is the bundle format +
  `run_on_robot.sh` (uses `lerobot-rollout --policy.path=...` from the LeLab venv).
* **D8 RBAC mapping.** PLAN §3.1 lists global roles admin/member/viewer and workspace roles
  owner/admin/member/viewer. Contract: platform admin = `users.is_platform_admin`; all data
  permissions come from the workspace role (`memberships.role`, lookup table `roles`).
  Workspace creation is platform-admin-only in v1.
* **D9 Held-out split.** Implemented by Hibiscus (seeded episode sample stored on the run) and
  passed as `--dataset.episodes=[train…]`, not via lerobot's `--dataset.eval_split`, so the split
  is explicit, reproducible and identical for eval/export. Normalisation stats still come from the
  full dataset's `meta/stats.json` (lerobot behaviour) — documented, accepted.
* **D10 Mixed precision.** `--accelerator.mixed_precision={no,fp16,bf16}` (0.7.1). `policy.use_amp`
  is excluded from forms (deprecated). P40 forced to `no`.
* **D11 Policy matrix additions** (PLAN silent): TD-MPC requires `next.reward` in the dataset
  (golden dataset has none → preflight blocks) and has no ONNX in v1; VQ-BeT ONNX samples codes
  through an explicit `sampling_noise` input because the PyTorch model uses `torch.multinomial`.
* **D12 Extra tables** beyond PLAN §4: `workspaces`, `memberships`, `invites` (requested),
  `recovery_codes`, `one_time_tokens`, `upload_parts`, `jobs` (validate/export/eval/import/merge/
  hub/estimate queue), `gpu_telemetry`, `resource_estimates`, `user_secrets`,
  `notification_channels`. `roles` exists as a seeded lookup table.
* **D13 Cross-workspace access returns 404**, never 403 (no existence oracle); PAT naming another
  workspace gets 403 `forbidden` (the token's own workspace is known to the caller).
* **D14 Worker package layout.** `worker/` is one uv project with top-level packages `train`,
  `validate`, `export`, `eval`, `core` (so tests live at `worker/train/tests` as requested);
  imports are `from train.log_patterns import …`.

## 3. Deployment facts (binding for A8, A2, A4)

* Public hostname: **https://robot.example.com**, via an existing **remotely-managed
  Cloudflare Tunnel**; `cloudflared` runs on the host as a systemd service (token-based). Its
  ingress currently points at `localhost:8000`.
* **Port 8000 is LeLab's default backend port** (LeLab has no auth and drives robot hardware).
  Hibiscus must never use 8000 on the host. The Hibiscus public entrypoint is the reverse-proxy
  container (serves the SPA, proxies `/api/*`, `/healthz`), published as
  **`127.0.0.1:18000` → container, plain HTTP**. No other Hibiscus port is published on a non-loopback
  interface. The tunnel origin must be changed to **`http://localhost:18000`** by the user in the
  Cloudflare dashboard (remotely-managed tunnel; no local config file). Agents must not read,
  copy or modify anything under `~/.cloudflared` and never handle the tunnel token.
* Inside Docker: API container listens on `api:8000` on the internal network only (container
  port, not published); `/metrics` and `/readyz` are not routed by the proxy (404 from outside).
  Postgres/Redis/MinIO are internal-only. Optional loopback-only admin ports (A8's choice, e.g.
  Grafana `127.0.0.1:13000`), never routed through the tunnel unless protected by Cloudflare Access.
* OpenAPI `servers`: `https://robot.example.com/api/v1`, `http://127.0.0.1:18000/api/v1`,
  dev `http://localhost:8080/api/v1`.
* **Cloudflare Access** (Zero Trust team exists): optional extra gate for the admin surface. If
  enabled, the Access application must cover both SPA `/admin*` and API `/api/v1/admin*`; the API
  then also validates `Cf-Access-Jwt-Assertion` (team domain + AUD from settings
  `HIBISCUS_CF_ACCESS_TEAM_DOMAIN`, `HIBISCUS_CF_ACCESS_AUD`). App-level auth (session + 2FA for
  admins) stays mandatory regardless.
* Real client IP: the proxy/API trust `CF-Connecting-IP` only when the TCP peer is the Docker
  network gateway of the published port (i.e. the request came through the host's loopback port,
  where only cloudflared and local processes can connect); otherwise the socket peer is used.
* TLS terminates at Cloudflare; origin is HTTP on loopback. The app still sends HSTS/CSP headers
  and `Secure` cookies (browsers see HTTPS; `localhost`/`127.0.0.1` count as secure contexts for
  local access).
* SSE through Cloudflare: `Cache-Control: no-cache`, `X-Accel-Buffering: no`, heartbeat 15 s,
  proxy buffering off for `text/event-stream`, proxy read timeout ≥ 1 h.
* Upload parts ≤ 64 MiB (Cloudflare 100 MB body limit); proxy `client_max_body_size` 70 MiB on
  `/api/v1/uploads/*/parts/*`, 1 MiB elsewhere.
* GPU workers: one container per GPU (`device_ids: ["0"]` → cuda0 RTX 3060, `["1"]` → cuda1 P40),
  shared host volumes mounted at identical paths `/cache` and `/scratch` (run-lifecycle §10);
  one CPU worker for validate/import/merge/hub jobs. `stop_grace_period: 120s` on workers.

## 4. Resolved decisions (user, 2026-11-15) — binding for all agents

1. **Email provider = Cloudflare Email Service** (sending). Implement `EmailSender` provider
   `cloudflare` as the production default: the API POSTs a signed JSON request
   (HMAC-SHA256 over body + timestamp, 5-min replay window) to a small Cloudflare Worker that
   owns the `send_email` binding; Worker source + `wrangler.toml` live in
   `deploy/cloudflare/email-worker/` (A8 owns it, A2 owns the client). Keep `smtp` and `none`
   (admin-generated links) providers for dev/tests. SPF/DKIM/DMARC records documented in
   `docs/runbook/email.md`. Availability of Email Service on the user's account is NOT yet
   verified — the `none` fallback must keep every flow usable.
2. **First platform admin bootstrap**: CLI one-time link (`python -m app.admin.bootstrap --email <e>`) — accepted.
3. **Pause semantics D2**: accepted as specified.
4. **Cloudflare Access for /admin**: supported in code, off by default — accepted.
5. **H.264 preview clips: YES.** Validation generates low-res H.264 (≤480p, CRF 28) per-episode
   preview clips + thumbnails; original AV1 untouched. `browser_playable_hint` stays for the
   originals; UI plays the H.264 preview.
6. **Pi0/Pi0.5 LoRA on P40**: stays `experimental` until the M3 smoke test proves it.
7. **Worker outbound Hub downloads: allowed**, cached in `/cache/hf`.
8. **Default quotas**: 1 concurrent run/user, 200 GPU-h/month, 200 GiB/workspace, 50 GiB/upload — accepted.
9. **VQ-BeT ONNX** may slip to v1.1 — accepted; ACT is the golden path.

## 5. Change requests

Agents append here (never edit contract files directly). Format:
`CR-<n> | <date> | <agent> | <file/section> | <problem> | <proposed change> | status (open/accepted/rejected by A1)`.


### CR-A2-1: Email Worker wire protocol (A2 client <-> A8 Worker) — status: open
- Requested by: A2 (agent/A2-auth)   Date: 2026-11-15
- File(s): docs/CONTRACT_NOTES.md §4.1 (no OpenAPI change); implementation `backend/app/core/email.py`
- Problem: §4.1 fixes "HMAC-SHA256 over body + timestamp, 5-min replay window" but not the exact
  headers / canonical string / body, so A2 (client) and A8 (Worker) can diverge.
- Proposal (what A2 implemented): `POST <HIBISCUS_EMAIL_WORKER_URL>`, `Content-Type: application/json`,
  headers `X-Hibiscus-Timestamp: <unix seconds>` and
  `X-Hibiscus-Signature: v1=<hex(HMAC-SHA256(HIBISCUS_EMAIL_WORKER_SECRET, "<timestamp>." + raw_body))>`;
  body `{"message_id": uuid, "from": str, "to": str, "subject": str, "text": str, "html": str|null,
  "reply_to": null}`. The Worker rejects |now - timestamp| > 300 s, compares in constant time,
  should de-duplicate on `message_id`, and answers 2xx on success (any other status => the API
  logs a delivery failure; flows stay usable through admin links). Reference verifier:
  `app.core.email.verify_signature`.
- Breaking: no — A8's Worker must follow it (or A8 proposes another format and A2 adapts).

### CR-A2-2: document 403 csrf_failed on POST /auth/logout — status: open
- Requested by: A2   Date: 2026-11-15
- File(s): api/openapi.yaml (paths./auth/logout)
- Problem: logout lists only 204, but it takes `X-CSRF-Token`; a live session without a matching
  token gets 403 `csrf_failed` (prevents forced logout by a cross-site request).
- Proposal: add `'403': {$ref: '#/components/responses/Forbidden'}` to `logout`.
- Breaking: no (additive).

### CR-A2-3: notifications endpoints have no owner — status: open
- Requested by: A2   Date: 2026-11-15
- File(s): docs/OWNERSHIP.md; api/openapi.yaml tag `notifications`
- Problem: `/users/me/notification-channels*` and `/notifications*` are not assigned to any agent.
  A2 did not implement them.
- Proposal: assign in Phase 3 (A4 emits run notifications; A2's `app.core.email.EmailSender` and
  `app.core.crypto.DataCipher` are ready for the email channel / encrypted targets).
- Breaking: no.

### CR-A2-4: registerWithInvite should document 404 invite_invalid — status: open
- Requested by: A2   Date: 2026-11-15
- File(s): api/openapi.yaml (paths./auth/register-invite)
- Problem: an unknown/revoked invite token yields `invite_invalid`, whose catalogue status is 404,
  but the operation lists 201/400/409/410/422/429 only (found by schemathesis).
- Proposal: add `'404': {$ref: '#/components/responses/NotFound'}` to `registerWithInvite`.
- Breaking: no (additive). A2 returns 404 `invite_invalid` meanwhile.

### CR-A2-5: validation failures on operations without a documented 422 — status: open (informational)
- Requested by: A2   Date: 2026-11-15
- File(s): api/openapi.yaml (e.g. `login`, `loginSecondFactor`, `verifyEmail`, `forgotPassword`,
  2FA ops, many workspace/admin ops)
- Problem: these operations take bodies/params but list no 422; FastAPI's default is 422.
- What A2 does: such routes carry `openapi_extra=app.core.errors.VALIDATION_400` and render
  request-validation failures as **400 `bad_request`** with `errors[]` (documented `BadRequest`).
  Other agents can use the same marker. Alternative for A1: add 422 to those operations.
- Breaking: no.

CR-A3-1 | 2026-11-15 | A3 | backend/app/db/models.py `DatasetVersion` vs openapi `DatasetVersion.error_code` | OpenAPI exposes `error_code` (e.g. `upload_checksum_mismatch`, `dataset_version_duplicate`) but `dataset_versions` has no such column | add `dataset_versions.error_code VARCHAR(64) NULL`. Adapter until then: API derives it from the newest dataset job (`jobs.error_code`, kinds validate/import/merge) | open

CR-A3-2 | 2026-11-15 | A3 | models.py `Job` vs openapi `Job.stage` | OpenAPI `Job.stage` has no column | add `jobs.stage VARCHAR(64) NULL`. Adapter: worker writes `jobs.result.stage` (heartbeat merges `{"stage": ...}` into `result`), API serializes `stage = result.stage`; A4's `/jobs` serializer should do the same | open

CR-A3-3 | 2026-11-15 | A3 | openapi `getDatasetMedia` 206 response | 206 lists only `application/octet-stream`; browsers' `<video>` seeking needs the real type | allow `video/mp4`, `image/jpeg`, `application/json` under 206 (implementation already sends the file's real Content-Type for 200 and 206) | open

CR-A3-4 | 2026-11-15 | A3 | openapi ErrorCode `dataset_version_duplicate` [409] / `completeUpload` | the content hash is only known after the worker unpacks, so completion cannot return 409 | document: duplicate content is reported asynchronously - version `failed`, `error_code = dataset_version_duplicate`, job `result.duplicate_of = <version id>` (that is what is implemented) | open

CR-A3-5 | 2026-11-15 | A3 | openapi `ValidationIssue.code` | no code for "archive format/filter not allowed" or "encrypted archive" | implemented as `archive_corrupt` with `params.reason` in {`format_not_allowed`, `filter_not_allowed`, `encrypted`, `read_error`, `empty`}; optional: add `archive_format_unsupported` to the issue enum | open

CR-A3-6 | 2026-11-15 | A3 | docs/spec/run-lifecycle.md 10 / ADR-0004 (dataset object layout) | spec names only `hibiscus-datasets/<ws>/<ds>/<ver>/` | record: that prefix holds exactly the content-hashed LeRobot root; derived artefacts live in the sibling prefix `<ver>.derived/` (`previews/<cam>/episode_XXXXXX.{mp4,jpg}`, `episodes/episode_XXXXXX.json`, `manifest.json` with every dataset file's path/size/sha256 + content_hash). GPU workers download `<ver>/` using `manifest.json` and can verify the hash | open


### CR-A4-1: draccus value quoting in the argv (policy-schema.md §4 step 5)
- Requested by: A4 (agent/A4-train)   Date: 2026-11-15
- File(s): docs/spec/policy-schema.md §4 step 5, docs/spec/run-lifecycle.md §10
- Problem: verified on lerobot-train 0.7.1: `--accelerator.mixed_precision=no` is parsed by draccus as
  YAML `False` and rejected (`mixed_precision must be one of 'no', 'fp16', 'bf16', got 'False'`); the
  single-quoted form `'no'` works for fresh runs but fails with `--resume=true` (`got "'no'"`).
  YAML 1.1 also reads `1e-05` as a string.
- Proposal: normative serialisation = strings that YAML would re-type (`no/yes/on/off/true/null/1.5/""`)
  are JSON double-quoted (`"no"`, verified fresh + resume), floats always carry a decimal point
  (`1.0e-05`). Implemented in `backend/app/runs/argv.py::fmt_value` and `worker/train/argv.py`.
- Breaking: no (spec clarification).

### CR-A4-2: lerobot 0.7.1 is not on PyPI
- Requested by: A4   Date: 2026-11-15
- File(s): ADR-0003, CONTRIBUTING §2 ("Pinned runtime in worker/")
- Problem: `uv` cannot resolve `lerobot[training]==0.7.1` from PyPI. The reference venv
  (`~/lelab/leLab/.venv`) was installed from git commit `fe1c54594f6ba275fccf210b9f7b11f0e2324b89`.
- Proposal: `worker/pyproject.toml` keeps `lerobot[training]==0.7.1` and adds
  `[tool.uv.sources] lerobot = { git = "https://github.com/huggingface/lerobot.git", rev = "fe1c545..." }`
  (done; `uv.lock` resolves torch 2.15.0+cu132). A8's worker image must build from this lock.
- Breaking: no.

### CR-A4-3: no columns for `RunCreate.export` and `init_from.hf_repo_id`
- Requested by: A4   Date: 2026-11-15
- File(s): backend/app/db/models.py (`runs`)
- Problem: `Run.export` (ExportOptions) and `InitFrom.hf_repo_id` must survive until export / the
  worker's `preparing`, but `runs` only has `init_from_model_id` / `init_from_checkpoint_id`.
- Workaround (implemented): stored inside `runs.config` as `config._export` and `config._init_from`;
  the API never returns keys starting with `_` (`Run.config` stays `{policy, train}`).
- Proposal: add `runs.export_options JSONB NOT NULL DEFAULT '{}'` and `runs.init_from_hf_repo_id VARCHAR(200)`.
- Breaking: no (additive).

### CR-A4-4: no warning code for a failed export (D3)
- Requested by: A4   Date: 2026-11-15
- File(s): api/openapi.yaml `RunWarningEvent.code`, `Model.error_message`
- Problem: run-lifecycle §5 asks for "`warning` event + notification `model.failed`" when export logic
  fails, but `RunWarningEvent.code` has no fitting value; `models` has no `error_message` column while
  `Model.error_message` exists in the API.
- Workaround: the `model` run event carries `status=failed`; notification `model.failed` is inserted;
  `Model.error_message` is read from `models.verification.error_message` (A5 may write it there).
- Proposal: add `export_failed` to `RunWarningEvent.code`; add `models.error_message TEXT`.
- Breaking: no (additive).

### CR-A4-5: `--dataset.repo_id` value
- Requested by: A4   Date: 2026-11-15
- File(s): api/policy-schemas/train.json `x-hibiscus.managed_by_hibiscus`, run-lifecycle §10
- Problem: train.json says `local/<dataset_version_id>`, run-lifecycle §10 / RunManifest example say
  `local/<dataset_slug>`. Implemented: `local/<dataset_slug>` (readable, matches the manifest example).
- Proposal: regenerate train.json note to `local/<dataset_slug>`.
- Breaking: no.

### CR-A4-6: pause requested at the final checkpoint
- Requested by: A4   Date: 2026-11-15
- File(s): docs/spec/run-lifecycle.md §2 (T4/T7)
- Problem: if `pause` lands while the last `save_freq` checkpoint is also the final step, the process
  exits 0 in status `pausing`; T4 is only defined from `running`.
- Implemented: T7 `pausing -> paused` with `resume_checkpoint_step = total_steps`; the resumed
  attempt skips training and goes straight to `exporting` (same path as an export-only infra retry).
- Proposal: document this in §3.
- Breaking: no.

### CR-A4-7: Tesla P40 cannot run the pinned torch (BLOCKER for cuda1)
- Requested by: A4   Date: 2026-11-15
- File(s): ADR-0003 / CONTRIBUTING §2 (torch 2.15 pin), PLAN §3.3 policy x GPU matrix, A8 worker image
- Problem: measured on this box: `torch 2.15.0+cu132` (the only build in both `worker/.venv` and
  `~/lelab/leLab/.venv`) ships kernels for `sm_75 sm_80 sm_86 sm_90 sm_100 sm_120` only. The P40 is
  `sm_61`: every CUDA op fails with `torch.AcceleratorError: CUDA error: no kernel image is available
  for execution on the device` (seen in `_preprocess_dataset_batch` of lerobot-train). CUDA 13 dropped
  Pascal, so no cu13x build will ever run on it.
- Proposal: the cuda1 worker image installs a torch 2.15 build compiled for sm_61 (e.g. a cu126 wheel
  if one exists for 2.15, else the newest torch whose cu126 wheel supports sm_61, pinned separately for
  that image) and the golden E2E runs on both images. Until then the scheduler must not place work on
  cuda1: set `gpu_nodes.status = disabled` for cuda1 (`PATCH /admin/gpus/cuda1`). The worker's
  `gpu_error` classification already catches this (infra, one retry, then failed).
- Breaking: no API change; deployment/ADR decision needed from A1/A8/user.

### CR-A4-8: SmolVLA fine-tuning needs `rename_map`
- Requested by: A4   Date: 2026-11-15
- File(s): api/policy-schemas/train.json, `RunCreate.config.train`
- Problem: measured: `lerobot-train --policy.path=lerobot/smolvla_base` on the golden dataset fails with
  `Feature mismatch ... Missing features: observation.images.camera1..3, Extra features:
  observation.images.wrist_cam` and asks for `--rename_map`. With
  `--rename_map={"observation.images.wrist_cam":"observation.images.camera1"}` it trains fine
  (20 steps bs 8 fp32 on the RTX 3060: torch peak 2.34 GB, 2646 MiB NVML, 0.177 s/step).
  train.json has no `rename_map`, so the `finetune` preset for smolvla cannot succeed.
- Proposal: add `rename_map: object<string,string>` (`x-hibiscus-cli: --rename_map`) to train.json, and a
  preflight check comparing the dataset camera keys with the pretrained config's image features.
- Breaking: no (additive).


### CR-A5-1: OpenAPI `OnnxStatus` lacks `skipped`
- Requested by: A5 (agent/A5-export)   Date: 2026-11-15
- File(s): api/openapi.yaml (`components.schemas.OnnxStatus`), docs/spec/bundle.md §3
- Problem: MANIFEST `checks.onnx_status` has `skipped` (ExportOptions.onnx=false on an ONNX-capable
  policy) but the API enum is `not_supported|pending|exporting|passed|failed`; the DB/API cannot
  represent "user did not ask for ONNX" without lying (`not_supported`).
- Proposal: add `skipped` to `OnnxStatus`. Until accepted, `BundleResult.api_onnx_status` maps
  `skipped -> not_supported` and A4 should set `onnx_detail = "ONNX export not requested"`.
- Breaking: no (additive enum value; FE/CLI must render it).

### CR-A5-2: `onnx/` presence rule when export or parity crashes
- Requested by: A5   Date: 2026-11-15
- File(s): docs/spec/bundle.md §2 ("onnx/ present only when onnx_status = passed | failed")
- Problem: if `torch.onnx.export` or the parity run itself raises, there is no parity report and
  possibly no graph; shipping a half-filled `onnx/` would mislead users.
- Proposal (implemented): `onnx/` is shipped iff `onnx/parity_report.json` exists. Crash ->
  `onnx_status=failed`, no `onnx/`, reason in `models.onnx_detail` / `verification.details`
  (`export: …` / `parity: …`). Parity *miss* -> `onnx/` kept with `parity_report.passed=false`.
- Breaking: no (clarification).

### CR-A5-3: run_on_robot.sh second block cannot be `lerobot-record --policy.path`
- Requested by: A5   Date: 2026-11-15
- File(s): docs/spec/bundle.md §8
- Problem: in LeRobot 0.7.1 `lerobot-record` is data-collection only; `--policy.path` is rejected
  ("unrecognized arguments", verified with LeRobot's parser) and the script says "For
  policy-based deployment, use lerobot-rollout instead".
- Proposal (implemented): the commented variant is
  `lerobot-rollout --strategy.type=episodic --policy.path=… --dataset.repo_id=local/eval_<bundle>
  --dataset.single_task=… --dataset.fps=… --dataset.num_episodes=10 --dataset.push_to_hub=false`.
  Both generated commands are parsed by LeRobot 0.7.1's own CLI parser in
  `worker/export/tests/test_bundle.py::test_run_on_robot_parses_with_lerobot_cli`.
- Breaking: no.

### CR-A5-4: VQ-BeT `sampling_noise` shape/semantics
- Requested by: A5   Date: 2026-11-15
- File(s): docs/spec/bundle.md §4.2
- Problem: the VQ-BeT head draws codes for `n_obs_steps + n_action_pred_token - 1` query tokens
  and `vqvae_num_layers` (not always 2) layers; only the token at `n_obs_steps-1` reaches the
  rollout output.
- Proposal (implemented): input `sampling_noise [batch, n_action_pred_token, vqvae_num_layers]`
  feeds the current+future tokens; history tokens use a fixed u=0.5 inside the graph (their
  outputs are discarded by `rollout=True`). Spec text should say `vqvae_num_layers` instead of `2`.
- Breaking: no for default configs (vqvae_num_layers=2).

### CR-A5-5: §4.1 MIN_MAX/QUANTILE formulas vs LeRobot
- Requested by: A5   Date: 2026-11-15
- File(s): docs/spec/bundle.md §4.1
- Problem: spec writes `max(max - min, eps)`; LeRobot 0.7.1 uses `where(max - min == 0, eps, max - min)`.
- Proposal (implemented): follow LeRobot exactly (spec says "identical to lerobot"); fix the text.
- Breaking: no.

### CR-A5-6: parity_report `max_rel_diff` and DDPM `full_denoise_loop` definitions
- Requested by: A5   Date: 2026-11-15
- File(s): docs/spec/bundle.md §6
- Problem: `max_rel_diff` is undefined; for DDPM "same initial noise" is insufficient because
  diffusers' `DDPMScheduler.step` adds fresh variance noise at every t>0.
- Proposal (implemented): `max_rel_diff = max |onnx - torch| / (|torch| + atol)` (bounded near 0).
  Full loop: the numpy loop draws the initial sample and each step's variance noise in order from
  `np.random.default_rng(0)`; the PyTorch reference (`policy.diffusion.conditional_sample`) gets the
  same draws injected into diffusers' `randn_tensor`, so both runs use identical noise.


### CR-A6-1: SPA routes for e-mailed / admin-generated links
- Requested by: A6 (agent/A6-fe)   Date: 2026-11-15
- File(s): api/openapi.yaml (descriptions of `InviteCreated.accept_url`, `adminCreatePasswordResetLink`, `forgotPassword`, `resendVerificationEmail`); affects A2's link builder
- Problem: the contract does not say which SPA URL a link must open, so A2 and A6 can drift.
- Proposal: document the SPA routes the FE implements: `https://<host>/invite?token=<t>` (also `/invite/<t>`), `https://<host>/reset-password?token=<t>`, `https://<host>/verify-email?token=<t>`. The FE also accepts `#token=<t>` (keeps tokens out of proxy/access logs) — recommend A2 uses the fragment form.
- Breaking: no — documentation only.

### CR-A6-2: `Notification.link` format
- Requested by: A6   Date: 2026-11-15
- File(s): api/openapi.yaml (components.schemas.Notification.link: "SPA path")
- Problem: unclear whether the path includes the workspace prefix.
- Proposal: specify a full SPA path `/w/<workspace_slug>/runs/<run_id>` (FE also accepts a workspace-relative `/runs/<id>` and prefixes the current workspace).
- Breaking: no.

### CR-A6-3: `ApiTokenCreate.expires_in_days` loses `null` in generated clients
- Requested by: A6   Date: 2026-11-15
- File(s): api/openapi.yaml (components.schemas.ApiTokenCreate.expires_in_days)
- Problem: `type: [integer, 'null']` together with `default: 90` makes openapi-typescript 7.5 emit `expires_in_days?: number` (null dropped), so "never expires" cannot be typed; FE uses a narrow type assertion.
- Proposal: drop `default: 90` from the schema and state "omitted => 90 days" in the description (server behaviour unchanged).
- Breaking: no.

### CR-A6-4: platform admins need to list all workspaces
- Requested by: A6   Date: 2026-11-15
- File(s): api/openapi.yaml (admin tag)
- Problem: `/admin/workspaces/{id}/quotas` needs a workspace id, but `GET /workspaces` lists only the caller's memberships; the admin quota page cannot reach other workspaces.
- Proposal: add `GET /admin/workspaces` (operationId `adminListWorkspaces`, cursor-paginated `Workspace`-like items with member_count/usage).
- Breaking: no (additive).

### CR-A6-5: tail of a finished run's log
- Requested by: A6   Date: 2026-11-15
- File(s): api/openapi.yaml (components.parameters.RangeHeader, getRunLogs)
- Problem: `RangeHeader` pattern `^bytes=[0-9]+-[0-9]*$` forbids suffix ranges and no log size is exposed, so the UI cannot show "last 64 KiB" of a finished run without downloading the whole log (current workaround: "Load log" fetches it all; live runs use SSE `log.byte_offset` + Range for earlier chunks).
- Proposal: allow `bytes=-<n>` (suffix range, RFC 9110) on `getRunLogs`, or add `Run.log_size_bytes`.
- Breaking: no.

### CR-A6-6: enumerate `PreflightCheck.code`
- Requested by: A6   Date: 2026-11-15
- File(s): api/openapi.yaml (components.schemas.PreflightCheck.code)
- Problem: free string; FE localises via `preflight.code.<code>` → `errors.<code>` → `run.warning.<code>` and falls back to the English `message`.
- Proposal: `code: oneOf [ErrorCode, RunWarningEvent.code, 'ok']` so A7 can write copy for every value.
- Breaking: no.

### CR-A6-7: YAML typo in `DatasetVersion.error_code` description
- Requested by: A6   Date: 2026-11-15
- File(s): api/openapi.yaml (DatasetVersion.allOf[1].properties.error_code)
- Problem: the unquoted description `(e.g. upload_checksum_mismatch, unpack_failed)` is parsed as a flow mapping, producing a stray key `"unpack_failed)": null` in the property schema.
- Proposal: quote the description string.
- Breaking: no.


CR-A7-1 | 2026-11-15 | A7 (agent/A7-cx) | api/openapi.yaml `PolicySummary.onnx_reason_key` (served by A4 `listPolicies`/`getPolicy`) | The contract says the field is "i18n key explaining missing ONNX" but fixes no values, so A4 and A7 could diverge | Values are `policy.onnx_reason.<policy_type>` for tdmpc, smolvla, pi0, pi05 (and vqbet while its ONNX slips to v1.1, CONTRACT_NOTES §4.9); `null` for act/diffusion. A7 already ships these keys in `frontend/src/i18n/{vi,en}/policy.json`. Non-breaking (documentation of values) | open

CR-A7-2 | 2026-11-15 | A7 (agent/A7-cx) | api/openapi.yaml `Notification.params` (A2/A4 producers) | `params` is "i18n interpolation params" with no names; UI copy needs fixed names or placeholders render literally | Fix param names per kind: run.* → `run_number` (int), `run_name`; model.* → `model_name`; dataset.* → `dataset_name`, `version` (int); invite.accepted → `user_name`, `workspace_name`; quota.warning → `percent` (int), `workspace_name`. Used by `notifications.kind.*`. Non-breaking (additive description) | open

CR-A7-3 | 2026-11-15 | A7 (agent/A7-cx) | docs/spec/bundle.md §8 (A5 `run_on_robot.sh`) | §8 asks for "a second commented block … `lerobot-record --policy.path=...`". In LeRobot 0.7.1 (verified in `~/lelab/leLab/.venv`: `lerobot-record --help` contains no `policy` option at all) recording with a policy moved to `lerobot-rollout`, whose recording strategies require `--dataset.*` (`rollout/configs.py`: `episodic` has `dataset_mode = "required"`) | Replace the commented block with `lerobot-rollout --strategy.type=episodic --policy.path="$HERE/pretrained_model" <same robot/camera flags> --dataset.repo_id=<user>/eval_<dataset> --dataset.single_task="<task>" --dataset.num_episodes=10`. User guide (`docs/user-guide/*/06-*`) and copy `models.run_on_robot.lerobot_record` already describe this. Non-breaking for API; affects A5 template | open

CR-A7-4 | 2026-11-15 | A7 (agent/A7-cx) | api/openapi.yaml `Model.name` example | Example `so101_picknplace_act-42-step10000` contradicts bundle.md §1 / CONTRACT_NOTES D4 (`<model_name>-r<run_number>-step<N>`, e.g. `so101_picknplace_act-r42-step10000`) | Change the example to `so101_picknplace_act-r42-step10000`. Docs/UAT/user guide use the `-r42-` form. Non-breaking | open

CR-A7-5 | 2026-11-15 | A7 (agent/A7-cx) | docs/spec/policy-schema.md §3 | i18n keys are specified only for policy fields (`policy.<type>.<field>.label/.help`); train.json fields have no convention | Document `policy.train.<field>.label/.help` for every `train.json` property (A7 ships all 13). Non-breaking | open

CR-A7-6 | 2026-11-15 | A7 (agent/A7-cx) | api/openapi.yaml `Problem.params` for `quota_exceeded` | One `quota_exceeded` code covers five different quotas; the UI can only say "a quota", which is less actionable (PLAN §6 "mọi lỗi có thông điệp hành động được") | Optional `params.quota` ∈ {`concurrent_runs`, `queued_runs`, `gpu_hours`, `storage`, `upload_size`} (+ `limit`, `used` numbers). A7 will add `errors.quota_exceeded.message_<quota>` variants once accepted; until then the generic message is used. Non-breaking (optional field) | open

CR-A7-7 | 2026-11-15 | A7 (agent/A7-cx) | api/openapi.yaml `adminUpdateUser` summary vs `AdminUserUpdate` | Summary says "force 2FA" but the schema has no such field (only `is_active`, `is_platform_admin`, `unlock`, `reset_mfa`); PLAN §3.1 "admin có thể bắt buộc 2FA" | Either add `require_mfa: boolean` (A2) or drop "force 2FA" from the summary. UI copy currently offers only `reset_mfa` (`admin.users.reset_mfa`). Non-breaking either way | open


CR-A8-1 | 2026-11-15 | A8 | ADR-0003 / worker image pins (torch 2.15) | torch 2.15.0 is only published for CUDA 13.2/13.4 and its kernels start at sm_75 (`torch.cuda.get_arch_list()` in the LeLab reference venv: sm_75..sm_120). The Tesla P40 (cuda1, sm_61) cannot run it at all. | `worker-cuda1` uses a separate image variant `worker-gpu-pascal` with **torch 2.14.1+cu126 / torchvision 0.29.1 / torchcodec 0.16.0** (verified: arch list contains sm_60; lerobot 0.7.1 accepts torch >=2.7,<2.16; AV1 decode + LeRobotDatasetMetadata on the golden dataset work in that image). Run manifests must record the per-GPU torch version; A4/A5 golden E2E must run on both GPUs. ADR-0003 note needed. | open
CR-A8-2 | 2026-11-15 | A8 → A4 | worker/pyproject.toml (`lerobot[training]==0.7.1`) | lerobot 0.7.1 is **not on PyPI** (latest there: 0.7.0); `uv lock`/`pip install` of worker/pyproject.toml fails. The LeLab venv installed it from git commit fe1c54594f6ba275fccf210b9f7b11f0e2324b89 (dist-info direct_url.json). | A4 adds `[tool.uv.sources] lerobot = { git = "https://github.com/huggingface/lerobot.git", rev = "fe1c54594f6ba275fccf210b9f7b11f0e2324b89" }` (keeps `==0.7.1`) and commits uv.lock. Until then the worker Dockerfile installs the URL requirement directly. Also: torch must come from different indexes per image variant (see CR-A8-1), so the images do not use `uv sync --locked` for the torch stack. | open
CR-A8-3 | 2026-11-15 | A8 | api/openapi.yaml `servers[2]` (dev `http://localhost:8080/api/v1`) | The dev stack is published on `127.0.0.1:18100` (port policy 18100-18199; 8080 is not used by any Hibiscus compose file). | Change the dev server URL to `http://127.0.0.1:18100/api/v1`. Non-breaking (documentation only). | open
CR-A8-4 | 2026-11-15 | A8 → all | test infrastructure (testcontainers MinIO image) | Upstream MinIO no longer publishes images: `minio/minio` (Docker Hub) and `quay.io/minio/minio` are not pullable on this host. testcontainers' default MinIO image will fail. | Use `pgsty/minio:RELEASE.2026-08-04T00-00-00Z` (maintained community build of the same server; `mc`: `pgsty/mc:RELEASE.2026-11-12T00-00-00Z`) in tests and compose (`HIBISCUS_MINIO_IMAGE` override available). | open
CR-A8-5 | 2026-11-15 | A8 → A2 | CONTRACT_NOTES §3 "Real client IP" | Refinement of who checks what: the TCP peer seen by the API is always the proxy, so the "peer is the Docker gateway" check happens in Caddy (`trusted_proxies <edge gateway>/32`, `client_ip_headers CF-Connecting-IP`). Caddy overwrites `X-Forwarded-For`, `X-Real-IP` and `CF-Connecting-IP` with the verified client IP. | The API trusts those headers **only** when the socket peer is the proxy's fixed address `HIBISCUS_TRUSTED_PROXY_IPS` (default 172.31.251.2); uvicorn runs with `--proxy-headers --forwarded-allow-ips $HIBISCUS_TRUSTED_PROXY_IPS`, so `request.client.host` is already the real client IP. Verified end to end in deploy/tests/test_stack_smoke.py (spoofed header from a non-gateway peer is ignored). | open


### CR-A9-1: FeatureSpec.names multi-type breaks the generated Python client
- Requested by: A9 (agent/A9-cli)   Date: 2026-11-15
- File(s): api/openapi.yaml (components.schemas.FeatureSpec.properties.names)
- Problem: `names: {type: [array, object, 'null']}` is rejected by openapi-python-client (0.26.2 and
  0.30.0: "Invalid property in union"); `FeatureSpec` is dropped and the generated `DatasetVersion`
  model imports a module that does not exist, so `getDatasetVersion` cannot be used through the
  generated client. Local adapter: `cli/hibiscus/api.py::get_dataset_version` calls the endpoint via
  the raw httpx layer and returns the JSON object.
- Proposal: `names: {oneOf: [{type: array, items: {type: string}}, {type: object, additionalProperties: true}, {type: 'null'}]}`
  (verified: the generator then emits FeatureSpec and a working DatasetVersion).
- Breaking: no (same instances validate).

### CR-A9-2: binary bodies need `format: binary` for openapi-python-client
- Requested by: A9 (agent/A9-cli)   Date: 2026-11-15
- File(s): api/openapi.yaml (`uploadPart` requestBody; `getModelFile` / `downloadModel` /
  `downloadDatasetVersion` responses)
- Problem: schemas `{type: string, contentMediaType: ...}` (OAS 3.1 style) are generated as
  `body: str` + `body.payload` (crashes) for `uploadPart`; `application/zip` responses are omitted.
  Local adapter: the CLI sends parts and streams downloads with httpx directly (same paths/headers).
- Proposal: add `format: binary` next to `contentMediaType` (allowed in 3.1, ignored by JSON Schema
  validators); verified that `uploadPart` then takes a `File` body.
- Breaking: no.

### CR-A9-3: `number` filter on listRuns
- Requested by: A9 (agent/A9-cli)   Date: 2026-11-15
- File(s): api/openapi.yaml (paths./runs.get parameters)
- Problem: users address runs as `#42`; the CLI resolves the number by paging `GET /runs` (200 per page,
  up to 50 pages). Works, but O(runs).
- Proposal: optional query `number: {type: integer, minimum: 1}` (exact match).
- Breaking: no.

### CR-A9-4: Python 3.10 floor for cli/
- Requested by: A9 (agent/A9-cli)   Date: 2026-11-15
- File(s): docs/CONTRIBUTING.md §2 (Python 3.12 for backend/, worker/, cli/; ruff target py312)
- Problem: the task requires the CLI to run on collect machines with Python >= 3.10 (Ubuntu 22.04
  ships 3.10.12). cli/ uses `requires-python >= 3.10`, ruff `target-version = py310`, mypy
  `python_version = 3.10`, and pins openapi-python-client 0.26.2 (0.27+ emits `typing.Self`, 3.11+).
  Tests pass on both 3.12 and 3.10.12.
- Proposal: document the cli/ exception in CONTRIBUTING §2.
- Breaking: no.

### CR-BE-N1: notification delivery tracking (schema, migration 0002) — status: open
- Requested by: backend (notifications, Phase 3)   Date: 2026-11-15
- File(s): backend/app/db/models.py (`Notification.dispatched_at`, new `NotificationDelivery`),
  backend/app/db/migrations/versions/0002_notification_delivery.py, docs/db-schema.md
- Problem: PLAN §3.4 needs email/webhook delivery with retries, but `notifications` had no delivery
  state and producers (train worker) only INSERT rows. Without state the dispatcher cannot know what
  was sent, retry with backoff, or record failures; multiple API replicas could double-send.
- Implemented: `notifications.dispatched_at TIMESTAMPTZ NULL` (fan-out marker, partial index where
  NULL; migration backfills existing rows = `created_at` so history is never replayed) and table
  `notification_deliveries(id, notification_id FK CASCADE, channel_id FK CASCADE, status
  pending|sent|failed, attempts, next_attempt_at, last_error, sent_at, timestamps)`, unique per
  (notification, channel). Dispatcher: API lifespan, leader-elected `pg_try_advisory_lock(7002)`,
  claims rows (`FOR UPDATE SKIP LOCKED` + `next_attempt_at = now()+claim_ttl`) before sending.
- Breaking: no (additive; worker INSERTs unchanged).

### CR-BE-N2: testNotificationChannel failure response — status: open
- File(s): api/openapi.yaml `testNotificationChannel`
- Problem: only 202/401/404/429 are documented; a delivery that fails (remote 4xx/5xx, timeout,
  target now resolving to a private address, email provider `none`) has no documented status.
- Implemented: 202 only when the message was actually delivered; otherwise 503
  `service_unavailable` with a sanitized `detail` (status code / error class only — the remote
  response body is never echoed, no read oracle) and `params.reason` for SSRF refusals.
  Rate limit: 5/min and 30/h per user => 429 `rate_limited` + `Retry-After`.
- Proposal: add `'503': {$ref: '#/components/responses/ServiceUnavailable'}` (or a Problem response).
- Breaking: no.

### CR-BE-N3: audit actions for notification channels — status: open
- File(s): api/openapi.yaml `AuditAction`, docs/db-schema.md §Audit
- Problem: no `notification_channel.*` action exists; using a new value would break
  `adminListAuditEvents` response validation.
- Implemented: create/delete are recorded as `secret.updated` with `target_type =
  notification_channel`, `target_id = <channel id>`, `details = {op: notification_channel.created |
  notification_channel.deleted, kind[, events]}` (never the target).
- Proposal: add `notification_channel.created`, `notification_channel.deleted` to `AuditAction`.
- Breaking: no (additive).

### CR-BE-N4: `NotificationChannelCreate.target` rules (document) — status: open
- File(s): api/openapi.yaml `NotificationChannelCreate.target`
- Implemented (all failures 422 `validation_failed`, `errors[0].loc = ["body","target"]`, `code` =
  reason): `email` must equal the caller's own **verified** account address (`email_not_own`,
  `email_not_verified`, `email_invalid`; delivery goes to the account address at send time, so an
  email change stops delivery — no third-party relay). `discord`: https URL on
  discord.com/discordapp.com/ptb./canary. with path `/api/webhooks/` (`discord_url_invalid`).
  `webhook`: https only (`https_required`), no userinfo (`url_userinfo`), resolvable
  (`dns_failed`), every resolved address public (`address_not_allowed`: loopback, RFC1918,
  link-local/metadata, CGNAT, multicast, reserved, ULA, IPv4-mapped/6to4/NAT64/Teredo wrappers).
  `telegram`: `<bot_token>:<chat_id>` split on the last `:` (`telegram_target_invalid`). At most 10
  channels per user (`errors[0].loc = ["body"]`, code `max_channels`). Duplicate `events` are de-duplicated.
  `target_hint` formats: `o***@example.com`, `discord.com/api/webhooks/…/abcd`, `host/…abcd`,
  `telegram chat …7890`.
- Breaking: no (documentation).

### CR-BE-N5: per-user `notification` events on the workspace SSE stream — status: open
- File(s): api/openapi.yaml `streamWorkspaceEvents` / `WorkspaceStreamEvent`
- Problem: notifications belong to one user but the stream is per workspace; broadcasting would
  leak one member's notifications to all members.
- Implemented: the dispatcher publishes `{"event": "notification", "user_id": <uid>, "data":
  Notification}` on `hibiscus:ws:<ws>` after fan-out; the stream drops envelopes addressed to another
  user. `app.core.events.publish_workspace_event(..., user_id=...)` is the helper.
- Breaking: no.

### CR-BE-N6: mid-run GPU-hour quota (run-lifecycle §6 `quota_exceeded`) — status: open (informational)
- File(s): worker/train/runner.py, worker/train/quota.py, backend/app/runs/router.py (resume)
- Implemented per §6 ("paused (`next_checkpoint`) instead of failed"): every
  `HIBISCUS_QUOTA_CHECK_INTERVAL_S` (60 s) the worker evaluates exactly the API's rule
  (`preflight.effective_quota` + `gpu_hours_this_month`, per creator within the workspace). When
  exhausted: `running -> pausing` (worker-initiated, `reason = error_code = quota_exceeded`,
  `desired_state` untouched), training continues to the next `save_freq` checkpoint, which is
  uploaded, then `pausing -> paused` with `resume_checkpoint_step` = that checkpoint and
  `runs.error_code = quota_exceeded`. Exhausted already when an attempt starts (training not yet
  started): `preparing -> pausing -> paused` without spawning (export-only attempts are not blocked).
  Resume is refused by the API while the quota is exhausted (existing 403 `quota_exceeded`); a
  successful resume from `paused` now clears `error_code`. Cancel / pause-now by the user still win.
- Notification: kind `quota.warning` with `params = {percent (>=100), workspace_name, reason:
  quota_exceeded, used_h, limit_h, run_id, run_number}`, link `/runs/<id>`.
- Proposal: (a) allow worker-initiated T6 `running|preparing -> pausing` with reason
  `quota_exceeded` in run-lifecycle §2; (b) optionally add `quota.warning` to
  `NotificationChannelCreate.events` so it can go to external channels (today in-app only).
- Breaking: no.

### CR-A8-P5-1: deploy env names = settings field names; Email Worker accepts the API body — status: implemented (fix/p5-deploy)
- File(s): deploy/docker-compose.yml, deploy/compose.dev.yml, deploy/.env.example,
  deploy/scripts/gen-secrets.sh, deploy/cloudflare/email-worker/src/message.ts; no change to
  api/openapi.yaml (no HTTP API shape changed).
- Problem: QC-e2e-01/03/09/10 — compose set names nothing reads (`HIBISCUS_S3_ACCESS_KEY_ID`,
  `HIBISCUS_EMAIL_CF_*`, `HIBISCUS_SMTP_URL`, `HIBISCUS_SESSION_COOKIE_SECURE`,
  `HIBISCUS_LOG_FORMAT`, `HIBISCUS_GPU_NODE_ID`, `HIBISCUS_GPU_DEVICE_INDEX`,
  `HIBISCUS_WORKER_JOB_KINDS`, ...), `HIBISCUS_ENV=production|development` failed
  `Literal["prod","dev","test"]`, and `HIBISCUS_JWT_PRIVATE_KEY` / `HIBISCUS_CURSOR_SECRET` were never
  supplied. SEC-infra-1 — the Worker rejected the API's `from` key and `null` html/reply_to.
- Decision: the application settings are the source of truth. Compose passes exactly
  `HIBISCUS_<field>` of backend `Settings` (api, migrate), worker `core.settings.WorkerSettings`
  (GPU workers: `HIBISCUS_GPU_INDEX`, `HIBISCUS_NVML_INDEX=0`) and `validate.settings` (worker-cpu,
  which now runs `HIBISCUS_WORKER_MODULE=validate`). `deploy/tests/test_env_contract.py` fails on any
  other name and instantiates the real settings from the rendered compose env. Email wire format v1
  is unchanged on the API side; the Worker now ignores `from` (sender fixed by `MAIL_FROM`) and
  treats `null` as absent. The exact request bytes are pinned by
  `deploy/cloudflare/email-worker/test/fixtures/api-send-requests.json`, used by both
  `backend/tests/contract/test_email_worker_contract.py` and the Worker's vitest suite.
- Operator action: rename in `deploy/.env` — `HIBISCUS_S3_ACCESS_KEY_ID`→`HIBISCUS_S3_ACCESS_KEY`,
  `HIBISCUS_S3_SECRET_ACCESS_KEY`→`HIBISCUS_S3_SECRET_KEY`, `HIBISCUS_EMAIL_CF_WORKER_URL`→
  `HIBISCUS_EMAIL_WORKER_URL`, `HIBISCUS_EMAIL_CF_HMAC_SECRET`→`HIBISCUS_EMAIL_WORKER_SECRET`,
  `HIBISCUS_SMTP_URL`→`HIBISCUS_SMTP_{HOST,PORT,USERNAME,PASSWORD,STARTTLS,SSL}`,
  `HIBISCUS_DATASET_CACHE_MAX_GB`→`HIBISCUS_DATASET_CACHE_MAX_BYTES`, `HIBISCUS_ENV=prod`; add
  `HIBISCUS_JWT_PRIVATE_KEY`, `HIBISCUS_CURSOR_SECRET`, `HIBISCUS_BACKUP_PASSPHRASE` (gen-secrets.sh).
- Breaking: deploy/.env only (compose refuses to render with the old secrets missing).

## Phase 5 worker fixes (branch fix/p5-worker, QC phase 4 findings)

### CR-A4-W1: monthly GPU-hour usage = GPU time used this month (QC-backend-03) — status: open
- File(s): worker/train/quota.py `USED_SECONDS_SQL`, backend/app/runs/preflight.py
  `gpu_hours_this_month` (same statement; they must agree).
- Problem: `sum(runs.gpu_seconds) WHERE coalesce(finished_at, now()) >= month_start` added the whole
  lifetime `gpu_seconds` of every unfinished (paused / queued) run to every month, so a quota-paused
  run locked its owner out of resume and new runs in all later months.
- Now: per run `least(gpu_seconds, seconds spent in an active status since month_start)`, where the
  active intervals come from the run's `status` events (`run_events.data.to`, ordered by `seq`,
  clipped to the month; an open interval ends at `now()`). Paused / queued runs add nothing while
  they wait; a run spanning the month boundary counts only this month's part.
- Not changed: `backend/app/workspaces/quotas.py` (usage display) still uses the old formula; it
  should call `preflight.gpu_hours_this_month` (backend owner).
- Breaking: no (same API shape; numbers are lower and correct).

### CR-A5-W1: `Verification.lelab_compatible`, MANIFEST `checks.lelab_*` (QC-ml-1) — status: open
- File(s): api/openapi.yaml `Verification`, api/bundle-schemas/manifest.schema.json `checks`,
  worker/export/{bundle,verify,load_check,lelab_compat,model_card,run_on_robot}.py.
- Problem: the load check ran in the worker interpreter (every LeRobot extra installed), so a
  Diffusion bundle was "verified" with "LeRobot load: ok" while it fails in the documented LeLab venv
  (LeRobot 0.7.1, no `diffusers` / `transformers`; checked read-only on ~/lelab/leLab/.venv).
- Now: the load check first runs "as LeLab": with `HIBISCUS_EXPORT_LOAD_CHECK_PYTHON` (a LeLab
  interpreter) or, by default, in the worker interpreter with the packages LeLab lacks hidden from
  the import system (`--block-modules`; same LeRobot commit, verdict matches the real LeLab venv for
  ACT and Diffusion, tested). If that fails the worker-env check decides `load_ok`.
  New optional fields: `Verification.lelab_compatible` (boolean|null), MANIFEST
  `checks.lelab_compatible`, `checks.lelab_check` (`lelab_venv`|`emulated`),
  `checks.lelab_requirements` (pip requirement strings, e.g. `diffusers>=0.38.0,<0.40.0`).
  `verified` is unchanged (LeRobot 0.7.1 loads the bundle); MODEL_CARD's Status row says
  "LeLab venv: needs extra packages: pip install ..." and run_on_robot.sh pre-checks the imports.
- Breaking: no (optional additions; old bundles have no `lelab_*` keys).

### CR-A5-W2: io_spec `action.temporal_ensemble_coeff` (QC-ml-2) — status: open
- File(s): api/bundle-schemas/io_spec.schema.json, worker/export/io_spec.py,
  worker/export/templates/infer_onnx.py.
- ACT trained with `temporal_ensemble_coeff` runs the model every step and blends overlapping
  chunks. io_spec now carries the coefficient (null for other policies / when unset) and
  `infer_onnx.py`'s `OnnxPolicy.select_action` implements LeRobot's `ACTTemporalEnsembler`
  (tested step by step against LeRobot `select_action`).
- Breaking: no (optional field).

### CR-A4-W2: worker env names (QC-e2e-03, QC-e2e-09) — status: open (deploy to align)
- Canonical names are documented in worker/core/settings.py. The worker also accepts what compose
  sets today: `HIBISCUS_GPU_DEVICE_INDEX` (= `HIBISCUS_GPU_INDEX`), `HIBISCUS_GPU_NODE_ID`,
  `HIBISCUS_S3_ACCESS_KEY_ID` / `HIBISCUS_S3_SECRET_ACCESS_KEY`, `HIBISCUS_S3_BUCKET_*`,
  `HIBISCUS_WORKER_HEARTBEAT_SECONDS`, `HIBISCUS_WORKER_LEASE_TTL_SECONDS`,
  `HIBISCUS_DATASET_CACHE_MAX_GB`, `HIBISCUS_VERSION`, `HIBISCUS_WORKER_HEARTBEAT_FILE` (now
  written by every worker loop and heartbeat, QC-e2e-08). With one visible GPU NVML index 0 is used
  automatically. `python -m train` runs the CPU validator when `HIBISCUS_WORKER_KIND=cpu`.
- Breaking: no.

### CR-A4-W3: GPU job handlers (QC-backend-02) — status: open (informational)
- `export_model` (export + `verify_only` re-verification) in worker/export/jobs.py, `eval_checkpoint`
  in worker/eval/jobs.py (writes `checkpoints.eval_metrics`, publishes an OpenAPI `EvalEvent`), and
  `push_model_hub` in the CPU worker (worker/validate/hub_push.py: repo root = `pretrained_model/`
  + README.md (model card with Hub front matter) + MANIFEST.json, `onnx/` when `include_onnx`;
  sets `models.hub_repo_id` / `hub_pushed_at`). Jobs keep their lease with `core.jobs.JobKeeper`.
- Still backend side: `exportCheckpoint` returns an existing `failed` model with 200 instead of
  re-enqueueing (QC-backend-02 last paragraph).
- Breaking: no.

### CR-BE-P5-1: non-members get 404 on list/create endpoints too (tenancy, D13) — status: implemented
- File(s): api/openapi.yaml (Conventions; `listRuns`, `listModels`, `listJobs`, `listDatasets`,
  `createDataset`, `importHfDataset`, `mergeDatasets`, `listUploads` gain `'404'`),
  backend/app/runs/deps.py `workspace_role`, backend/app/datasets/access.py `require_workspace`
- Problem: core (`ensure_role`, workspaces router) answers 404 for a non-member, but runs/datasets
  answered 403 `forbidden` when the workspace id was named in the request, which told a stranger
  that the workspace exists.
- Implemented: a caller who is not a member of the named workspace gets 404 `not_found` on every
  endpoint (list, create, item). A PAT naming a workspace other than its own still gets 403
  `forbidden` on list/create (the token's workspace is known to its holder) and 404 on items.
- Breaking: status code only (403 -> 404) for non-members; clients branching on `forbidden` for
  "not a member" must treat `not_found` the same.

### CR-BE-P5-2: Idempotency-Key on createRun — atomic, re-authorised, per user + workspace — status: implemented
- File(s): backend/app/runs/router.py `create_run`, backend/app/db/models.py `Run.idempotency_key`,
  migration `0003_run_idempotency_key` (partial unique index `uq_runs_idempotency_key` on
  `(workspace_id, created_by, idempotency_key)`)
- Problem: SEC-auth-05 (a replay returned the stored run before any authorization: removed members,
  read-only or other-workspace PATs got it with 201) and QC-backend-06 (Redis check-then-set: concurrent
  retries created duplicate runs).
- Implemented: the request is authorised first (workspace role >= member, PAT bound to the body's
  workspace, `runs:write`), then the key is looked up in Postgres for (body.workspace_id, caller);
  the stored run is re-loaded through `load_run` before it is returned (201 + `Location`, body =
  current state of that run). A concurrent duplicate loses on the unique index and replays the
  winner's run. Keys older than 24 h are released on reuse (a new run is created). No Redis needed.
  `Idempotency-Key` must be 1..64 chars. `POST /uploads` keeps its sha256 natural resume (unchanged).
- Breaking: no.

### CR-BE-P5-3: `init_from.hf_repo_id` needs a platform allow-list (SEC-input-1) — status: implemented
- File(s): backend/app/runs/settings.py (`HIBISCUS_INIT_FROM_HF_ALLOWLIST`), preflight.py, router.py
- Problem: LeRobot imports and instantiates the processor classes named by a Hub repo's
  `policy_preprocessor.json`, so any member could run code on a GPU worker via
  `init_from.hf_repo_id`.
- Implemented: `HIBISCUS_INIT_FROM_HF_ALLOWLIST` (comma-separated or JSON list of `org/name`,
  case-insensitive, operator-managed; default empty) lists the approved repos. A repo not on the list
  makes preflight fail: check `init_from`, severity `error`, code `forbidden`,
  `params = {hf_repo_id, reason: "hf_repo_not_allowed"}` (so createRun / cloneRun -> 422
  `preflight_failed`). Resuming an older run whose repo is not (or no longer) approved -> 403
  `forbidden` with the same params. The worker still hardens loading (allow_patterns, no `class`
  steps) as defence in depth; an allow-listed repo is trusted but can change upstream.
- Breaking: yes for callers using `hf_repo_id` without an allow-list entry (by design).

### CR-BE-P5-4: push-hub answers 501 while no worker runs `push_model_hub` (QC-backend-02) — status: implemented
- File(s): api/openapi.yaml `pushModelToHub` (`'501'`, `components.responses.FeatureDisabled`,
  ErrorCode description), backend/app/models/router.py, backend/app/runs/settings.py
  (`HIBISCUS_HUB_PUSH_ENABLED`, default false)
- Problem: the API queued `push_model_hub` jobs (and audited `model.pushed_hub`) that no worker
  claims, so the push silently never happened.
- Implemented: after authorization, when `HIBISCUS_HUB_PUSH_ENABLED` is false the API returns 501
  `service_unavailable` with `params = {feature: "push_model_hub", reason: "feature_disabled"}`, no
  job and no audit row. Set the flag once a worker handles the job kind. No new ErrorCode (reuses
  `service_unavailable`; UI can branch on `params.reason`). `export_model` / `eval_checkpoint`
  stay enqueued (the worker implements their handlers). `exportCheckpoint` on a checkpoint whose
  live model is `failed` now retires that model (soft delete) and queues a new export (202).
- Breaking: no (a new error status for a feature that never worked).

### CR-BE-P5-5: exportCheckpoint under concurrency (QC-backend-07) — status: implemented
- File(s): backend/app/runs/router.py `export_checkpoint`, api/openapi.yaml (`'409'` documented)
- Implemented: the checkpoint row is locked (`SELECT ... FOR UPDATE`) before the live-model check,
  so concurrent requests get one 202 and 200s with the same model; a remaining unique-index race maps
  to 409 `conflict`, never 500.
- Breaking: no.

### CR-BE-P5-6: storage quota for HF import / merge, byte cap in CPU job payloads (SEC-input-3) — status: implemented (API side)
- File(s): backend/app/datasets/quota.py (new, shared helpers), api_datasets.py, api_uploads.py
- Implemented: `importHfDataset` -> 403 `quota_exceeded` (`params.kind = storage_bytes`) when the
  workspace has no storage left (repo size is unknown to the API); `mergeDatasets` -> the same when
  the sum of the sources' `size_bytes` does not fit. Job payloads carry `max_bytes` (int, bytes the
  job may store): `import_hf_dataset` and `merge_datasets` = quota left; `validate_dataset` = quota
  left counting this upload as consumed space released (caps archive expansion). Worker contract:
  fail the version with `quota_exceeded` when the download / extraction / output would exceed
  `max_bytes` (absent = no API cap, old jobs).
- Breaking: no.

### CR-BE-P5-7: `/policies` require `runs:read` on PATs — status: implemented
- File(s): api/openapi.yaml `listPolicies` / `getPolicy` (`patAuth: ['runs:read']`, `'403'`),
  backend/app/runs/policies.py; `listGpus` / `getQueue` already required it (now documented `'403'`).
- Breaking: PATs with only `datasets:*` / `models:read` can no longer read the policy catalogue
  (the CLI's `hibiscus train` uses `runs:write`, which implies `runs:read`).

### CR-BE-S1: phase-5 auth hardening (SEC-auth-01..04/06, QC-e2e-02/07) — status: open
- File(s): api/openapi.yaml (`previewInvite`, `acceptInviteToken`, `getInvitePreview`, `acceptInvite`,
  `login`, `refreshSession`, `changePassword`, `setupTotp`, `enableTotp`, `disableTotp`,
  `regenerateRecoveryCodes`, `streamWorkspaceEvents`, `streamRunEvents`); backend/app/auth,
  backend/app/core, backend/app/workspaces/router.py, backend/app/runs/stream.py
- Implemented:
  - **Invite token out of URL paths (SEC-auth-04).** New `POST /auth/invites/preview {token}` and
    `POST /auth/invites/accept {token}`. `GET /auth/invites/{token}` and
    `POST /auth/invites/{token}/accept` are `deprecated: true` (still served; the token segment is
    redacted to `REDACTED` in the API access log and in the Caddy access log filter). The SPA uses the
    body variants.
  - **2FA enrolment revokes other sessions; MFA roles need a 2FA-verified session (SEC-auth-01).**
    `enableTotp` revokes every other session family of the user (`revoked_reason=user_revoked`, audit
    `auth.mfa_enabled.details.other_sessions_revoked`). A session of a user with 2FA enabled and an
    owner/admin/platform-admin role that never passed 2FA gets 403 `mfa_reauth_required` everywhere
    except `/auth/me`, `/auth/2fa/*`, `/auth/logout`, `/auth/refresh` (same allow-list as enrolment).
    Admin `reset_mfa` already revoked all sessions.
  - **Re-auth limits (SEC-auth-02).** Password / TOTP checks by a logged-in session (`changePassword`,
    `setupTotp`, `enableTotp`, `disableTotp`, `regenerateRecoveryCodes`): 10 per 15 min per user
    (`HIBISCUS_RL_REAUTH_PER_15MIN`, 429), failures count towards the login lockout (423
    `account_locked` while locked) and are audited as `auth.login_failed` with
    `reason=reauth_bad_password|bad_second_factor`.
  - **No lockout oracle on login (SEC-auth-06).** A locked account answers 401
    `invalid_credentials` (same argon2 work, no `Retry-After`); attempts while locked do not extend
    the lock and are audited with `reason=locked`. `loginSecondFactor` keeps 423 (the caller already
    proved the password).
  - **SSE re-authorization (SEC-auth-03).** Workspace and run streams re-check the session (or PAT),
    the user and the workspace membership every `HIBISCUS_SSE_AUTH_RECHECK_S` (15 s) and close when
    any is gone; every stream closes after `HIBISCUS_SSE_MAX_LIFETIME_S` (15 min). EventSource
    reconnects by itself (run stream: with `Last-Event-ID`, no gap).
  - **Refresh after an aborted rotation (QC-e2e-07).** Access tokens carry an optional `rid` claim
    (the refresh row issued in the same response); a request carrying it marks that row used
    (`sessions.last_used_at`). A rotated refresh token whose successor was never used is rotated
    again (204 + new cookies) instead of revoking the family; reuse after the successor was used is
    still detected (401 `refresh_reuse_detected`). The SPA also no longer calls refresh from an SSE
    error while the page is unloading.
  - **Shared dev keys (QC-e2e-02).** Non-prod no longer generates per-process keys:
    `HIBISCUS_DEV_SECRET` derives JWT / data / cursor keys deterministically (HKDF), otherwise they
    are created once in `HIBISCUS_DEV_KEYS_FILE` (default `$XDG_RUNTIME_DIR/hibiscus-dev-keys.json`,
    else `<tmpdir>/hibiscus-dev-keys-<uid>.json`) and shared by every worker process of the
    container. The file is only trusted when it is a regular file (opened with `O_NOFOLLOW`) owned by
    the effective uid with mode 0600 (phase-5 re-verify N7); otherwise start-up fails. Explicit keys
    still win.
- Breaking: no (additive operations; the old invite operations are deprecated, not removed; `login`
  stops returning 423).
