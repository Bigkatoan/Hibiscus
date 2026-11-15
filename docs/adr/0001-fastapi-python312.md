# ADR-0001: FastAPI on Python 3.12 for the API

- **Status:** Accepted (2026-11-15)
- **Deciders:** A1 (Solution Architect)
- **Source:** PLAN.md §2, ADR-1

## Context

Hibiscus wraps LeRobot (pinned at 0.7.1, Python 3.12, torch 2.15) to train robot policies on two local
GPUs. Much of the API's domain knowledge lives in LeRobot itself: policy config dataclasses (draccus),
dataset v3.0 metadata (`meta/info.json`, `stats.json`), and feature schemas. The API must:

- expose policy JSON Schemas and presets derived from those dataclasses (see ADR-0005);
- pre-flight validate a run (dataset camera keys vs. policy `input_features`, VRAM estimate vs. GPU);
- stream large uploads/downloads and long-lived SSE connections (ADR-0010);
- publish an OpenAPI 3.1 contract from which TypeScript and Python clients are generated.

Translating LeRobot's schemas into another language would create a second source of truth that drifts
on every LeRobot upgrade (the failure mode already visible in LeLab's hard-coded CLI flags).

## Decision

- The API is a **FastAPI** application on **Python 3.12**, package `app` under `backend/`
  (`app/auth`, `app/workspaces`, `app/datasets`, `app/runs`, `app/models`, `app/admin`, `app/core`, `app/db`).
- Async stack: SQLAlchemy 2.x async + asyncpg (PostgreSQL 16), redis-py asyncio (Redis 7),
  an async S3 client for MinIO. Validation with **pydantic v2**. Migrations with Alembic.
- Base path is `/api/v1`. The contract is `api/openapi.yaml` (OpenAPI 3.1), owned by A1. FastAPI's
  generated schema is a build artifact used only for conformance checking, never the source of truth.
- Errors use RFC 9457 `application/problem+json` with a stable machine-readable `code` from the
  contract's error catalog.
- Backend imports LeRobot only for read-only introspection (config dataclasses, dataset metadata);
  it never trains in-process (ADR-0003).

## Consequences

### Positive
- Same language and version as LeRobot: schemas are read directly, no translation layer.
- First-class async I/O for streaming chunks to MinIO and holding many SSE connections.
- pydantic v2 models double as request validation and OpenAPI conformance checks.

### Negative
- The backend image carries LeRobot as a dependency for introspection (larger image). Backend must
  import it lazily and must not import torch at module import time on hot paths.
- Python CPU-bound work (archive unpacking, stats recomputation) must not run in the API process.

### Follow-ups agents must honor
- A2/A3/A4: route handlers live in their own sub-package; shared deps (DB session, current user,
  workspace membership, problem+json helpers) come from `app/core` only.
- Every endpoint response must validate against `api/openapi.yaml` in tests (see CONTRIBUTING DoD).
- CPU-heavy or GPU work is delegated to workers (`worker/validate`, `worker/train`, `worker/export`,
  `worker/eval`) via the run/job queue (ADR-0002), never `BackgroundTasks`.
- Structured JSON logging with `request_id` (and `run_id` when applicable) on every log line.
- `mypy --strict` and ruff must be clean for `backend/`.

## Rejected alternatives

- **Node.js / Go API:** would require re-implementing or exporting LeRobot's draccus schemas and
  dataset metadata parsing in another language; drifts on every LeRobot upgrade.
- **Django / DRF:** heavier, sync-first ORM; streaming and SSE are less natural.

## Related

- ADR-0002 (queue), ADR-0003 (training subprocess), ADR-0005 (policy form), ADR-0010 (upload/SSE)
- `api/openapi.yaml`, `backend/app/db/models.py`, `docs/OWNERSHIP.md`, `docs/CONTRIBUTING.md`
