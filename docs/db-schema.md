# Database schema v0.1 (PostgreSQL 16)

Source of truth: [`backend/app/db/models.py`](../backend/app/db/models.py) (SQLAlchemy 2.0 typed
models). This page explains it. Owner: A1. Changes only via contract change request.

## Conventions
* UUID v4 primary keys (Python-generated); BIGINT identity for append-only high-volume tables
  (`audit_events`, `run_events`, `gpu_telemetry`). `gpu_nodes.id` is a stable string (`cuda0`).
* `created_at` / `updated_at` (`timestamptz`, server default `now()`) on every table.
* Soft delete `deleted_at` on `workspaces`, `datasets`, `dataset_versions`, `models`; unique
  constraints on live rows are partial indexes `WHERE deleted_at IS NULL`.
* Enums = `VARCHAR(32)` + `CHECK` (non-native), values identical to OpenAPI enums (guarded by
  `backend/tests/contract/test_contract_consistency.py`).
* Constraint naming convention (`ix_`, `uq_`, `ck_`, `fk_`, `pk_`) is set on `Base.metadata` so
  Alembic autogenerate is deterministic. 27 tables, 186 named constraints/indexes, all unique and
  ≤ 63 chars (checked).
* Secrets at rest: passwords/recovery codes = argon2id PHC strings; refresh tokens, PATs, invite
  and one-time tokens = `sha256` (32 bytes, `bytea`); TOTP secret, HF token, notification targets
  = AES-256-GCM with the app data key (`HIBISCUS_DATA_KEY`, Docker secret).

## Migrations
Alembic lives in `backend/app/db/migrations/` (owner A1; generated at integration, Phase 3):
`0001_initial` = autogenerate from `models.py` **plus** hand-written SQL that autogenerate cannot
produce:
1. `INSERT INTO roles` seed: owner(40, mfa), admin(30, mfa), member(20), viewer(10).
2. Audit immutability trigger:
   `CREATE FUNCTION audit_events_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION
   'audit_events is append-only'; END $$ LANGUAGE plpgsql;` + `BEFORE UPDATE OR DELETE ON
   audit_events FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();` and
   `REVOKE UPDATE, DELETE ON audit_events FROM hibiscus_app`.
3. Same append-only trigger on `run_events`.
Agents develop against `Base.metadata.create_all()` on a testcontainers Postgres 16 and must not
add their own migrations; schema needs go through A1.

## Entity overview

```
users ─┬─< memberships >─ workspaces ─┬─< datasets ─< dataset_versions >─┐
       │        │ role → roles        ├─< invites                        │
       ├─< sessions (refresh families)├─< quotas (workspace / per user)  │
       ├─< api_tokens (PAT, 1 workspace)                                 │
       ├─< recovery_codes, one_time_tokens, user_secrets                 │
       ├─< notifications, notification_channels                          │
       │                              ├─< upload_sessions ─< upload_parts│
       │                              ├─< runs ──────────────────────────┘ (dataset_version_id)
       │                              │     ├─< run_events, run_metrics, gpu_telemetry
       │                              │     ├─< checkpoints ─< models (1 live model per checkpoint)
       │                              │     └── gpu_nodes (assigned / requested)
       │                              ├─< jobs (validate/export/eval/import/merge/hub/estimate)
       └─< audit_events (actor)       └─< audit_events (workspace)
resource_estimates (global cache)
```

## Tables

### Identity & auth (A2)
| Table | Key columns / constraints | Notes |
|---|---|---|
| `users` | `uq_users_email_lower` on `lower(email)`, `ck email = lower(email)`, `locale ∈ {vi,en}` | `is_platform_admin`, lockout (`failed_login_count`, `locked_until`), TOTP (`totp_secret_enc`, `totp_enabled_at`, `totp_last_used_step` for replay protection) |
| `recovery_codes` | FK user CASCADE | 10 rows per enrolment, `used_at` |
| `one_time_tokens` | `uq token_hash`, purpose ∈ email_verify / password_reset / mfa_challenge / email_change | password reset 30 min, verify 24 h, mfa challenge 5 min |
| `sessions` | `uq refresh_token_hash`, `family_id`, `replaced_by_id` | one row per refresh token; rotation = new row, old gets `rotated_at`; reuse of a rotated token ⇒ revoke family (`revoked_reason=refresh_reuse`); idle 7 d, absolute 30 d; `mfa_verified` |
| `api_tokens` | `uq token_hash`, `uq prefix`, `ck scopes ⊆ known`, non-empty | PAT bound to `workspace_id`; `hbp_<prefix>_<secret>` |
| `user_secrets` | `uq (user_id, kind)` | `hf_token` (encrypted) + 4-char hint |
| `audit_events` | BIGINT identity, hash chain (`prev_hash`, `hash`), indexes (workspace, created_at), (actor, created_at), (action, created_at) | append-only (trigger). Action catalogue = OpenAPI `AuditAction` |

### Workspaces (A2)
| Table | Key columns / constraints | Notes |
|---|---|---|
| `roles` | PK `name`, `uq rank` | seeded lookup (PLAN §4 `roles`) |
| `workspaces` | `uq slug` (live), slug regex check | `settings` JSONB = OpenAPI `WorkspaceSettings` |
| `memberships` | `uq (workspace_id, user_id)`, FK role → roles | |
| `invites` | `uq token_hash`, `ck role <> owner`, email lower-case | 72 h, single use (`accepted_at`), `revoked_at` |
| `quotas` | `uq (workspace_id, user_id) NULLS NOT DISTINCT` | `user_id NULL` = workspace default; per-user row overrides. Defaults: 1 concurrent run, 10 queued, 200 GPU-h/month, 200 GiB storage, 50 GiB per upload |

### Datasets & uploads (A3)
| Table | Key columns / constraints | Notes |
|---|---|---|
| `datasets` | `uq (workspace_id, slug)` live; `latest_version_id` (FK, use_alter) | slug also used as `repo_id = local/<slug>` |
| `dataset_versions` | `uq (dataset_id, version)`, `uq (dataset_id, content_hash)` live, `ck ready ⇒ content_hash, storage_prefix, total_episodes, features not null` | immutable once `ready`; `info`, `features`, `stats` verbatim from `meta/`; `validate_report` = OpenAPI `ValidationReport`; `preview` = `DatasetPreview`; `merged_from uuid[]` |
| `upload_sessions` | `ck part_size ∈ [5 MiB, 64 MiB]`, `ck part_count ∈ [1, 10000]`, `ck sha256 hex`, `ck exactly one of dataset_id / new_dataset_name` | S3 multipart id, `expires_at` slides +7 d per part |
| `upload_parts` | PK `(upload_id, part_number)`, `ck size ≤ 64 MiB` | per-part sha256 + S3 ETag |

`content_hash` = sha256 over the sorted lines `<relative path>\0<sha256(file)>\n` of the unpacked
dataset root (directory names normalised to `/`, no trailing slash).

### Runs, GPUs, metrics (A4) and models (A5)
| Table | Key columns / constraints | Notes |
|---|---|---|
| `gpu_nodes` | PK `id` (`cuda0`, `cuda1`), `uq (host, device_index)` | registered by workers; `supports_bf16`, `supports_fast_fp16`, heartbeat |
| `runs` | `uq (workspace_id, number)`; partial `ix_runs_queue (priority, queued_at) WHERE status='queued'`; partial `ix_runs_lease (lease_expires_at) WHERE active`; checks on priority, desired_state, heldout_fraction < 0.5, step range, `infra_retries_used ≤ 1`, single init source | also the queue row (ADR-2). `config` JSONB = `{policy, train}`; `resolved_args`; split arrays; lease fields; `last_event_seq` allocates `run_events.seq`; `manifest` = `RunManifest` |
| `run_events` | `uq (run_id, seq)`; level check | append-only; `seq` = SSE id; `data` = OpenAPI event payloads |
| `run_metrics` | PK `(run_id, key, step)`, `ix (run_id, step)`, key regex | upsert (resume may replay a step) |
| `gpu_telemetry` | `ix (gpu_node_id, ts)`, `ix (run_id, ts)` | 5 s NVML samples, 30-day retention |
| `checkpoints` | `uq (run_id, step)`, partial unique `is_last` per run | `has_training_state` only on latest |
| `models` | partial unique `checkpoint_id` (live), `ck verified ⇒ status=ready` | bundle uri/sha/size, `manifest` = MANIFEST.json, `verification`, `onnx_status`, Hub fields |
| `jobs` | partial `ix_jobs_queue (resource, priority, created_at) WHERE queued` | non-training work, same lease protocol |
| `resource_estimates` | `uq cache_key` | dry-run cache: key = sha256(policy_type, gpu_name, batch_size, mixed_precision, image_shapes, policy_config_hash, lerobot_version) |

### Notifications
| Table | Notes |
|---|---|
| `notifications` | in-app; partial index on unread; `kind` = OpenAPI `Notification.kind`; `params` = i18n params |
| `notification_channels` | email / discord / telegram / webhook, encrypted target, subscribed events |
| `notification_deliveries` | (migration 0002, CR-BE-N1) one row per notification x channel: `status` pending/sent/failed, `attempts`, `next_attempt_at` (backoff / claim), `last_error`, `sent_at`; `uq (notification_id, channel_id)`; partial index on due pending rows. `notifications.dispatched_at` marks fan-out done (partial index where NULL) |

## Audit action catalogue
Identical to OpenAPI `components.schemas.AuditAction` (auth.*, token.*, user.*, admin.*,
workspace.*, member.*, invite.*, dataset.*, dataset_version.*, run.created/cancelled/paused/resumed,
model.downloaded/file_downloaded/deleted/pushed_hub, secret.updated). `details` never contains
secrets, tokens or passwords; for downloads it carries `{bytes, range}`.

## Retention
`gpu_telemetry` 30 d; `run_events` / `run_metrics` kept with the run; `audit_events` ≥ 1 year
(never deleted by the app); expired `one_time_tokens`, `upload_sessions` (and S3 multipart
aborts) cleaned hourly by the API maintenance loop (A3/A2 own their tables' cleanup).
