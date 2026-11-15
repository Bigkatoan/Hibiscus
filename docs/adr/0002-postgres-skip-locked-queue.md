# ADR-0002: Job queue in PostgreSQL with `FOR UPDATE SKIP LOCKED`, one worker per GPU

- **Status:** Accepted (2026-11-15)
- **Deciders:** A1 (Solution Architect)
- **Source:** PLAN.md §2, ADR-2

## Context

Training jobs run for minutes to many hours on exactly two GPUs (cuda0 = RTX 3060 12GB, cuda1 = Tesla
P40 24GB). Run state must be durable across API and worker restarts (PLAN §6: restarting a worker or
the API mid-run must not lose the job; it resumes). Users must be able to cancel, pause and resume.
The scheduler must apply fair-share across workspace members (ADR-0009) and GPU constraints (P40 has
no bf16). We want as few moving parts as possible on a single host.

## Decision

- The queue **is** the `runs` table. A run with `status = 'queued'` is claimable.
- One **worker container per GPU**, each registered in `gpu_nodes` (device index, name, VRAM,
  capabilities such as `bf16`). A worker only claims runs it can execute.
- Claiming happens in one transaction:
  `SELECT ... FROM runs WHERE status='queued' AND <gpu filter> ORDER BY <fair-share order>
  FOR UPDATE SKIP LOCKED LIMIT 1`, then `UPDATE` to `preparing`, set `worker_id`, `gpu_node_id`,
  `lease_expires_at = now() + 60s`.
- **Lease:** the worker renews `lease_expires_at` with a heartbeat **every 10s**; **TTL is 60s**.
  A reaper (in the scheduler) treats an expired lease on a non-terminal run as an infrastructure
  failure: the run is re-queued (resuming from `checkpoints/last`) and retried at most once.
- Ordering (ADR-0009): `priority` (desc), then lowest decayed GPU-seconds of the owner over the
  trailing 7 days, then `queued_at` (asc) — docs/spec/run-lifecycle.md §7.1.
- GPU constraint: on a node without bf16 (P40) the scheduler forces
  `--accelerator.mixed_precision=no` and records the override as a `run_events` entry shown in UI.
- Control signals (cancel/pause) are columns/events in Postgres; Redis pub/sub is only a fast-path
  notification, never the source of truth.
- Lifecycle: `queued → preparing → running → exporting → succeeded | failed | cancelled`, plus
  `paused`. Full state machine in `docs/spec/run-lifecycle.md`.

## Consequences

### Positive
- Durable, transactional state; no broker to operate; trivially inspectable with SQL.
- Leases make crash recovery deterministic and testable (kill a worker, run resumes).
- Fair-share and GPU filtering are just SQL in one place.

### Negative
- Polling (with `LISTEN/NOTIFY` or Redis as a wake-up hint) instead of push delivery.
- Lease/heartbeat logic is ours to get right; clock source must be the DB (`now()`), not the worker.

### Follow-ups agents must honor
- A4: all state transitions go through one module in `app/runs` / `worker/train` that enforces the
  state machine in `docs/spec/run-lifecycle.md`; illegal transitions raise, never silently succeed.
- A4: heartbeat 10s, TTL 60s are configuration with these defaults; tests must cover lease expiry,
  double-claim prevention (two workers racing), and retry-once semantics (no retry on config errors).
- A10: destructive test "kill worker mid-run" must prove resume from `checkpoints/last`.
- No Celery/RQ/arq or other task framework may be added.

## Rejected alternatives

- **Celery (+Redis/RabbitMQ):** poor fit for multi-hour GPU tasks (visibility timeouts, ack
  semantics), hard to cancel and resume, adds a broker; state would be split across two systems.
- **Redis streams as queue:** not durable enough as the single source of run state.

## Related

- ADR-0003 (subprocess), ADR-0009 (fair-share), ADR-0001
- `docs/spec/run-lifecycle.md`, `backend/app/db/models.py` (`runs`, `run_events`, `gpu_nodes`)
