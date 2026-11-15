# ADR-0004: MinIO (S3 API) for all blob storage, multipart uploads

- **Status:** Accepted (2026-11-15)
- **Deciders:** A1 (Solution Architect)
- **Source:** PLAN.md §2, ADR-4 (transport refined by ADR-10)

## Context

Hibiscus stores multi-GB dataset archives, unpacked datasets, checkpoints, raw logs and model bundles.
Uploads must be resumable and shared between the browser and the `hibiscus` CLI. Storage should be
movable to a cloud S3 later without code changes. PLAN §6 requires MinIO versioning for backups.

PLAN's ADR-4 originally said "presigned multipart upload". ADR-10 (Cloudflare body limits, MinIO not
exposed publicly) changes only the **transport**: clients send chunks to the API, which writes each
chunk as an S3 multipart part. This ADR records the storage decision with that refinement applied.

## Decision

- **MinIO** is the only blob store, accessed exclusively through the S3 API. Buckets:
  - `hibiscus-uploads` — in-progress and completed raw uploads (archives), lifecycle-expired.
  - `hibiscus-datasets` — unpacked, validated, immutable dataset versions (content-hashed).
  - `hibiscus-artifacts` — checkpoints, logs (`train.log`, `metrics.csv`), eval output, bundles.
- Object keys are namespaced by workspace: `<workspace_id>/<kind>/<id>/...`.
- MinIO is **not exposed publicly**; only the API and workers reach it on the internal Docker network.
  No presigned URL is ever returned to clients.
- Uploads: an `upload_sessions` row maps 1:1 to an S3 multipart upload. Each client chunk (≤ 64 MiB)
  is one S3 part; sha256 is verified per part and for the whole file at completion (ADR-0010).
- Downloads (bundles, logs, dataset files) are streamed by the API from MinIO, supporting HTTP `Range`.
- Bucket versioning is enabled on `hibiscus-datasets` and `hibiscus-artifacts`.
- Dataset versions and bundles are immutable once written; deletion is soft in Postgres first.

## Consequences

### Positive
- One storage abstraction for API and workers; S3-compatible so it can move to AWS/R2 later.
- Native multipart gives resumable uploads with no extra server.
- Immutable, hashed objects make run reproducibility (`dataset@version`) cheap.

### Negative
- All upload/download bandwidth passes through the API process (accepted cost of ADR-0010).
- Orphaned multipart uploads must be aborted by a janitor job.

### Follow-ups agents must honor
- Only `app/core` provides the S3 client factory; bucket names come from settings, defaults as above.
- A3: abort incomplete multipart uploads on session expiry; integration tests use testcontainers MinIO.
- A4/A5: workers write artifacts under `hibiscus-artifacts/runs/<run_id>/{checkpoints,logs}/...` and bundles under
  `hibiscus-artifacts/models/<model_id>/<bundle_name>.zip`; datasets under `hibiscus-datasets/<workspace_id>/<dataset_id>/<version_id>/`
  (docs/spec/run-lifecycle.md §4, docs/spec/bundle.md §1).
  and record their sha256 in Postgres / `MANIFEST.json`.
- A8: MinIO ports are never published on the host or the tunnel; backups and versioning configured
  in `deploy/`.
- A11: verify that no endpoint leaks MinIO URLs or credentials.

## Rejected alternatives

- **tus server:** extra service, duplicates what S3 multipart already provides.
- **Local filesystem volumes:** no multipart/resume semantics, no path to cloud storage.
- **Presigned URLs straight to MinIO:** would require exposing MinIO to the Internet (see ADR-0010).

## Related

- ADR-0010 (chunked upload via API), ADR-0003, ADR-0009
- `docs/spec/bundle.md`, `backend/app/db/models.py` (`upload_sessions`, `dataset_versions`, `models`)
