# Run lifecycle, scheduling, worker lease (contract v0.1)

Owner: A1 (spec) · Implementers: A4 (`backend/app/runs/`, `worker/train/`), A5 (export/eval steps).
Related: ADR-0002 (Postgres queue), ADR-0003 (unmodified `lerobot-train`), ADR-0009 (fair-share),
`backend/app/db/models.py` (`Run`, `RunEvent`, `Job`, `GpuNode`, `Checkpoint`),
`docs/spec/log-parsing.md`, `docs/spec/bundle.md`.

Everything below is normative ("MUST") unless marked as a recommendation.

## 1. States

| Status | Meaning | Holds a GPU lease | Terminal |
|---|---|---|---|
| `queued` | Waiting for a GPU (also: re-queued for resume / infra retry) | no | no |
| `preparing` | Worker claimed it: download dataset, restore checkpoint, build argv, start process | yes | no |
| `running` | `lerobot-train` process is training (first tqdm/`Start offline training` line seen) | yes | no |
| `pausing` | Pause requested; waiting for next checkpoint (or killing for `pause_now`) | yes | no |
| `paused` | Process stopped; checkpoint `last` in MinIO; GPU released | no | no |
| `exporting` | Training finished; building bundle for the final checkpoint (+ eval, ONNX) | yes | no |
| `succeeded` | Training finished (model may be `ready` or `failed`, see §5) | no | yes |
| `failed` | Unrecoverable error (`error_code`) | no | yes |
| `cancelling` | Cancel requested on an active run; killing the process | yes | no |
| `cancelled` | Stopped by user | no | yes |

`runs.desired_state` (`run | pause | pause_now | cancel`) is the user's intent, written only by the
API. `runs.status` is the observed state, written by the lease holder (worker) except for the
transitions marked "API" below.

## 2. Transition table (exhaustive; anything else => 409 `run_invalid_transition`)

| # | From | To | Actor | Trigger |
|---|---|---|---|---|
| T1 | — | `queued` | API | `POST /runs`, `/clone` (preflight passed) |
| T2 | `queued` | `preparing` | worker | claim (§7) |
| T3 | `preparing` | `running` | worker | first `TQDM_RE` match or `TRAINING_START_RE` |
| T4 | `running` | `exporting` | worker | process exit 0 **and** final checkpoint uploaded |
| T5 | `exporting` | `succeeded` | worker | export job finished (model ready **or** failed) |
| T6 | `running`/`preparing` | `pausing` | API | `POST /pause` (sets desired_state) — worker acknowledges |
| T7 | `pausing` | `paused` | worker | checkpoint uploaded + process exited |
| T8 | `paused` | `queued` | API | `POST /resume` |
| T9 | `queued`/`paused` | `cancelled` | API | `POST /cancel` (no process exists) |
| T10 | `preparing`/`running`/`pausing`/`exporting` | `cancelling` | API | `POST /cancel` |
| T11 | `cancelling` | `cancelled` | worker | process group dead, scratch cleaned |
| T12 | any active | `queued` | worker or reaper | infra error with retry budget left (§6) or graceful worker shutdown (§8) |
| T13 | any active | `failed` | worker or reaper | non-retryable error, or retry budget exhausted |
| T14 | `failed` | `queued` | API | `POST /resume` when a checkpoint exists (`run_not_resumable` otherwise); resets `infra_retries_used` to 0 |
| T15 | `exporting` | `failed` | worker/reaper | infra failure during export after retry budget (training checkpoints remain; user can `POST /checkpoints/{step}/export`) |

Rules:
* Every transition is a single SQL `UPDATE runs SET status=:to, status_changed_at=now(), ... WHERE
  id=:id AND status=:from [AND lease_owner=:me]` (optimistic guard). 0 rows => lost race, re-read.
* Every transition inserts a `run_events` row `type='status'` (`RunStatusEvent`) in the same
  transaction, with `seq = (UPDATE runs SET last_event_seq = last_event_seq + 1 ... RETURNING last_event_seq)`,
  then publishes it on Redis (§9) **after commit**.
* `cancel` wins over `pause`: `POST /cancel` while `pausing` => `cancelling`.
* `POST /pause` on `queued` => 409 (cancel or just wait). On `pausing`: idempotent, but
  `mode=now` upgrades `pause` → `pause_now`.
* `POST /resume` on `paused` re-enters the queue with original priority and `queued_at = now()`.
* `allowed_actions` in the API response is derived from this table and the caller's role
  (member: own runs; admin/owner: all runs in workspace; viewer: none).

## 3. Pause / resume semantics (deviation from PLAN, see CONTRACT_NOTES §D2)

`lerobot-train` is run unmodified (ADR-3) and offers no "checkpoint now" signal. Therefore:

* `mode=next_checkpoint` (default): status `pausing`; the worker keeps the process running until
  the log shows `Checkpoint policy after step N` **and** the checkpoint directory
  `checkpoints/<N:06d>/` is complete (`training_state/training_step.json` exists and
  `checkpoints/last` points to it), uploads it (§4), then sends SIGTERM to the process group.
  UI shows `progress.next_checkpoint_step` and ETA.
* `mode=now`: SIGTERM immediately; progress since the last uploaded checkpoint is lost. If no
  checkpoint exists yet, the run goes to `paused` with `resume_checkpoint_step = null` and resume
  restarts from step 0 with the same seed and split.
* Resume = new attempt (`attempt += 1`) on any eligible GPU: restore
  `checkpoints/<last>/{pretrained_model,training_state}` from MinIO to the identical local path
  (§10) and run
  `lerobot-train --config_path=<out>/checkpoints/<NNNNNN>/pretrained_model/train_config.json --resume=true [--steps=<new total>] [--accelerator.mixed_precision=<effective>]`.
  `initial_step` for log parsing = `training_step.json.step`.
* Changing GPU type across resume is allowed; mixed precision is re-resolved for the new GPU
  (P40 => `no`) and a `warning` `mixed_precision_forced_no` event is emitted when it changes.

## 4. Checkpoint handling

* Worker passes `--save_checkpoint=true --save_freq=<train.save_freq>`; lerobot also saves at the
  final step. On each `CHECKPOINT_RE` match the worker waits for the directory to be complete
  (poll 1 s, timeout 10 min => `checkpoint_corrupt`), then uploads:
  `s3://hibiscus-artifacts/runs/<run_id>/checkpoints/<NNNNNN>/pretrained_model/**` (always) and
  `.../training_state/**` (only for the newest checkpoint; the previous checkpoint's
  `training_state/` is deleted after the new one is uploaded => `has_training_state` true only on
  `is_last`). Then inserts/updates `checkpoints` (`is_last` moves atomically) and emits a
  `checkpoint` event.
* Upload happens in a background thread while training continues; the next checkpoint upload
  waits for the previous one. Pause/exit waits for in-flight uploads.

## 5. Export (status `exporting`)

After process exit 0 the worker (same lease, same GPU) runs the export pipeline of
`docs/spec/bundle.md` for the final checkpoint: eval (if `export.eval`) → bundle → ONNX + parity
(if supported and `export.onnx`) → verification → zip upload. It creates the `models` row at start
(`status=building`). Outcomes:
* success => model `ready`, run `succeeded`.
* export *logic* failure (exporter exception, parity fail) => model `failed` (or `ready` with
  `onnx_status=failed`, not verified), run still `succeeded`, `warning` event + notification
  `model.failed`. Rationale: training artefacts are fine and re-export is possible.
* infra failure (worker lost, storage) => §6 retry rules; retry re-runs only the export (no
  training) because `current_step == total_steps` and the final checkpoint exists.

Extra exports / evals of other checkpoints are `jobs` rows (`export_model`, `eval_checkpoint`,
resource `gpu`), claimed by the same workers between runs (§7.3).

## 6. Failure classification and retry

Each attempt ends with exactly one `error_code` (or none on success). Classification order (first
match wins) using worker-observed facts:

| error_code | Class | Detection |
|---|---|---|
| `config_invalid` | user | process exit != 0 before `TRAINING_START_RE`, traceback contains `draccus`, `ValueError`, `NotImplementedError`, `TypeError` raised from `lerobot/configs` or `configuration_*.py` |
| `dataset_feature_mismatch` | user | traceback contains `KeyError: 'observation.` / feature validation errors (preflight should prevent) |
| `dataset_unavailable` | infra | dataset download from MinIO failed / content hash mismatch after download |
| `oom` | user | `OOM_RE` match; message suggests smaller batch_size; **not retried** |
| `nan_loss` | user | 3 consecutive metrics records with non-finite `loss` (first one => `warning nan_detected`); worker SIGTERMs |
| `stalled` | infra | no bytes on the process pipe for 15 min while `running` (warning `log_silent` at 5 min) |
| `gpu_error` | infra | `NCCL_OR_CUDA_FATAL_RE`, NVML reports GPU lost / Xid |
| `process_crashed` | infra | killed by a signal we did not send (exit < 0) or exit != 0 after training started without a better match |
| `storage_error` | infra | MinIO errors after 5 retries (checkpoint/log upload) |
| `checkpoint_corrupt` | infra | checkpoint incomplete / restore hash mismatch |
| `worker_lost` | infra | lease expired (reaper, §7.2) |
| `export_failed` | infra | only when export crashes for infra reasons and budget exhausted (T15) |
| `quota_exceeded` | user | monthly GPU-hours exhausted mid-run: run is paused (`next_checkpoint`) instead of failed; code used on resume rejection |
| `internal_error` | infra | anything else in worker code (bug) |

Retry rule (PLAN §3.3 "auto retry once on infra errors, never on config errors"):
* infra class and `infra_retries_used = 0` => T12 back to `queued` with `infra_retries_used = 1`,
  `resume_checkpoint_step = last uploaded checkpoint`, event `warning retrying_after_infra_error`.
* otherwise => T13 `failed`. User can still `POST /resume` (T14) if a checkpoint exists.
* A user-class error never auto-retries.
* `last 50 log lines` are stored in the `error` event (`log_excerpt`).

## 7. Queue, claim, lease, heartbeat

### 7.1 Claim (each GPU worker, poll every 2 s + wake on Redis `hibiscus:queue` notifications)

A worker owns exactly one `gpu_nodes` row (`id = cuda<index>`), registers it on start
(upsert name/VRAM/compute capability from NVML; `supports_bf16 = cc >= 8.0`,
`supports_fast_fp16 = cc >= 7.0`), sets `status=online`, `worker_id = <hostname>:<pid>:<boot uuid>`.
It claims at most one run at a time:

```sql
WITH usage AS (                       -- fair-share: decayed GPU time per user, last 7 days
  SELECT r.created_by AS user_id,
         sum(r.gpu_seconds * power(0.5, extract(epoch FROM now() - coalesce(r.finished_at, now())) / 86400.0)) AS score
  FROM runs r
  WHERE coalesce(r.finished_at, now()) > now() - interval '7 days'
  GROUP BY r.created_by
), active AS (
  SELECT created_by, workspace_id, count(*) AS n FROM runs
  WHERE status IN ('preparing','running','pausing','exporting','cancelling')
  GROUP BY created_by, workspace_id
)
SELECT r.id FROM runs r
LEFT JOIN usage u ON u.user_id = r.created_by
LEFT JOIN active a ON a.created_by = r.created_by AND a.workspace_id = r.workspace_id
WHERE r.status = 'queued'
  AND (r.requested_gpu_id IS NULL OR r.requested_gpu_id = :gpu_id)
  AND coalesce(r.required_vram_mb, 0) <= :gpu_total_vram_mb - 512        -- 512 MiB headroom
  AND r.policy_type <> ALL(:policies_unsupported_on_this_gpu)            -- §7.4
  AND coalesce(a.n, 0) < :effective_max_concurrent_runs(r.created_by, r.workspace_id)
ORDER BY r.priority DESC, coalesce(u.score, 0) ASC, r.queued_at ASC
LIMIT 1
FOR UPDATE OF r SKIP LOCKED;
```
then in the same transaction:
```sql
UPDATE runs SET status='preparing', gpu_node_id=:gpu_id, lease_owner=:worker_id,
       lease_expires_at = now() + interval '60 seconds', heartbeat_at = now(),
       attempt = attempt + 1, started_at = coalesce(started_at, now()), status_changed_at = now()
WHERE id = :id;
UPDATE gpu_nodes SET current_run_id = :id WHERE id = :gpu_id;
```
(`effective_max_concurrent_runs` = per-user quota row, else workspace row, else 1; implemented as a
SQL function or a pre-computed VALUES list; the claim query must stay one statement under lock.)
Priority > 0 is only settable by workspace admins; fair-share decides among equal priority.

### 7.2 Lease and heartbeat
* Lease TTL **60 s**; the worker heartbeats every **10 s**:
  `UPDATE runs SET lease_expires_at = now() + interval '60 seconds', heartbeat_at = now(),
  current_step = :step, latest_metrics = :m RETURNING desired_state` `WHERE id=:id AND lease_owner=:me`.
  0 rows => the worker lost the lease: kill the process group immediately, discard local state.
* The returned `desired_state` drives pause/cancel (also pushed instantly via Redis
  `hibiscus:control:<gpu_id>`; the DB value is authoritative).
* Reaper (runs inside the API process, leader-elected with `pg_try_advisory_lock(7001)`), every
  **15 s**: for runs in an active status with `lease_expires_at < now()`: apply §6 with
  `worker_lost` (T12/T13), set `gpu_nodes.current_run_id = NULL`. Same for `jobs`.
* `gpu_nodes.last_heartbeat_at` older than 30 s => API reports the GPU `offline`.

### 7.3 Jobs table
Non-training jobs use the identical protocol on `jobs` (`resource = 'gpu' | 'cpu'`). GPU workers
prefer runs over GPU jobs **except** `export_model`/`eval_checkpoint` jobs created by a user, which
are interleaved: when a worker becomes idle it claims a queued GPU job if the oldest such job has
waited ≥ 5 min or the run queue is empty. CPU jobs (`validate_dataset`, `import_hf_dataset`,
`merge_datasets`, `push_model_hub`) are claimed by the CPU worker container (`worker/validate`, A3)
with `max_attempts = 2`.

### 7.4 Policy × GPU eligibility (until replaced by measured matrix in M3)
| Policy | cuda0 RTX 3060 12 GB (cc 8.6) | cuda1 Tesla P40 24 GB (cc 6.1) |
|---|---|---|
| act, diffusion, vqbet, tdmpc | eligible | eligible (fp32 forced) |
| smolvla | eligible (limited: warn if batch_size > 8; bf16 recommended) | eligible, preferred when `gpu=auto` |
| pi0, pi05 | **not eligible** | eligible only with `train.peft` set (preflight `policy_requires_peft`) + `gradient_checkpointing=true` |

`gpu=auto` placement preference (soft, via `requested_gpu_id = NULL` plus ordering): the API sets
`requested_gpu_id` only when the user picks a GPU or the policy is eligible on exactly one GPU.

### 7.5 Mixed precision resolution
`effective = requested` if the GPU supports it (`bf16` needs `supports_bf16`, `fp16` needs
`supports_fast_fp16`), else `no` + warning `mixed_precision_forced_no`. Stored in
`mixed_precision_effective` and passed as `--accelerator.mixed_precision`.

## 8. Crash recovery and restarts

* **Worker crash / `docker kill`** (e.g. M3 test "kill worker mid-run"): lease expires within 60 s,
  reaper re-queues (infra retry #1) with `resume_checkpoint_step` = last *uploaded* checkpoint.
  The re-queued attempt resumes from MinIO on whichever GPU claims it.
* **Graceful worker stop** (SIGTERM to worker, `docker compose stop`, stop_grace_period 120 s):
  the worker stops claiming, sends SIGTERM to the training process group, uploads the newest
  complete checkpoint if not yet uploaded, sets run → `queued` (T12) with reason `worker_shutdown`
  **without** consuming the infra retry, releases the lease. Same for `exporting` (export restarts).
* **Worker restart with stale local state**: on boot the worker deletes `/scratch/runs/*` that do
  not belong to a run it currently holds.
* **API restart**: no run state lives in the API; SSE clients reconnect with `Last-Event-ID`.
* **Postgres restart**: worker DB calls retry with backoff for up to 50 s (< lease TTL); the
  training process keeps running meanwhile.
* **Redis loss**: live SSE degrades (no live `progress`/`log`); persisted events still flow from
  `run_events` (API polls table every 2 s when Redis is unavailable).
* **Process kill semantics**: the worker starts `lerobot-train` with `start_new_session=True`;
  kill = `os.killpg(pgid, SIGTERM)`, wait 30 s, then `SIGKILL` (dataloader workers are children).

## 9. Telemetry, events and log transport

* Process stdout+stderr merged, read in 64 KiB chunks, parsed per `docs/spec/log-parsing.md`.
* Persisted events (`status`, `metrics`, `checkpoint`, `warning`, `error`, `model`, `eval`) =>
  `run_events` row then Redis `PUBLISH hibiscus:run:<run_id>` with envelope
  `{"event": "<type>", "id": <seq>, "data": {...}}`.
  Metrics are also upserted into `run_metrics` (one row per key) in the same transaction.
* Ephemeral events => Redis only, no id: `progress` (throttled to 1/s), `log` (batched every 500 ms,
  ≤ 500 lines; tqdm `\r` frames are NOT forwarded, only `\n`-terminated lines), `telemetry` (5 s).
* Workspace stream: status changes are also published to `hibiscus:ws:<workspace_id>`.
* Raw log: worker writes `/scratch/runs/<id>/attempt-<n>.log` (tqdm frames collapsed: a run of `\r`
  segments is reduced to its last segment before a `\n`) and uploads it to
  `s3://hibiscus-artifacts/runs/<run_id>/logs/attempt-<n>.log` every 30 s and at exit;
  `runs.last_log_at` updated on every chunk read.
* NVML sampling every 5 s on the worker's GPU into `gpu_telemetry` (with `run_id` when busy) and
  as `telemetry` events. Retention 30 days (daily cleanup job by A8 cron).
* SSE endpoint latency target: metrics visible < 2 s after the log line (PLAN §6).

## 10. Worker filesystem and process contract

| Path (inside every worker container; identical across GPUs) | Purpose |
|---|---|
| `/cache/datasets/<dataset_version_id>/` | unpacked LeRobot dataset (LRU, max 150 GB, `.complete` marker + content hash check) |
| `/scratch/runs/<run_id>/output/` | `--output_dir` (must NOT exist before a fresh attempt) |
| `/scratch/runs/<run_id>/attempt-<n>.log` | raw log |
| `/scratch/exports/<model_id>/` | bundle build dir |

Fresh attempt argv (A4 builds it from `config` + policy schema `x-hibiscus-cli`):
```
lerobot-train \
  --policy.type=<policy_type> --policy.device=cuda --policy.push_to_hub=false \
  --policy.<field>=<value> ...                      # only fields present in config.policy
  --dataset.repo_id=local/<dataset_slug> --dataset.root=/cache/datasets/<version_id> \
  --dataset.episodes='[<train_episodes>]' \
  --output_dir=/scratch/runs/<run_id>/output --job_name=<run_id> \
  --steps=<n> --batch_size=<n> --seed=<n> --save_checkpoint=true --save_freq=<n> --log_freq=<n> \
  --num_workers=<min(train.num_workers, 4)> --accelerator.mixed_precision=<effective> \
  --trackio.enable=false [--policy.pretrained_path=<restored init_from dir>] [--peft.*=...]
```
Environment: `CUDA_VISIBLE_DEVICES` set by compose `device_ids` (inside: device 0),
`PYTHONUNBUFFERED=1`, `HF_HUB_OFFLINE=1` unless the run needs Hub downloads (`init_from.hf_repo_id`,
SmolVLA `vlm_model_name`, Pi0 tokenizer) — those are pre-fetched during `preparing` into
`/cache/hf` (`HF_HOME`). `TQDM_MININTERVAL` is left default.

Held-out split (PLAN §3.5): `n = len(episodes)`, `k = 0 if fraction == 0 else max(1, round(n * fraction))`
(and `k <= n - 1`); `heldout = sorted(random.Random(seed).sample(range(n), k))` unless explicit
`heldout_episodes`; `train_episodes` = the rest. Stored on the run at creation (never recomputed).
Note: normalisation stats come from the full dataset `meta/stats.json` (lerobot behaviour).

## 11. Reproducibility manifest

Written at `preparing` (attempt appended each attempt) to `runs.manifest`; schema
`RunManifest` in `api/openapi.yaml`. `image_digest` comes from env `HIBISCUS_IMAGE_DIGEST`
(set by A8 at build), versions from `importlib.metadata`.
