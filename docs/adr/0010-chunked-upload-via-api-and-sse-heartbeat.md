# ADR-0010: Chunked uploads through the API; SSE with heartbeat

- **Status:** Accepted (2026-11-15)
- **Deciders:** A1 (Solution Architect)
- **Source:** PLAN.md §2, ADR-10

## Context

Behind Cloudflare (ADR-0008) a request body is limited to **100 MB** and idle connections are dropped
after ~**100 s**. Datasets are multi-GB archives uploaded from the browser and the `hibiscus` CLI over
unreliable links. Live metrics/logs/run events must stream for hours. MinIO must stay private
(ADR-0004), so presigned URLs are not an option.

## Decision

### Uploads
1. `POST /api/v1/.../uploads` creates an `upload_sessions` row (filename, total size, total sha256,
   chunk size) and an S3 multipart upload in `hibiscus-uploads`. Server returns `upload_id` and
   `chunk_size` (≤ **64 MiB**; S3 minimum 5 MiB for all but the last part).
2. `PUT /api/v1/.../uploads/{upload_id}/parts/{part_number}` with the raw chunk body and header
   carrying the chunk's sha256. The API **streams** the body into S3 `UploadPart` (part = chunk),
   hashing on the fly; mismatch → part rejected with problem+json `code`. Idempotent per part number.
3. `GET .../uploads/{upload_id}` lists received parts → clients resume by sending only missing parts.
4. `POST .../uploads/{upload_id}/complete` → S3 `CompleteMultipartUpload`, whole-file sha256
   verified, then dataset version creation and validation job enqueue.
5. Sessions expire (default 7 days); a janitor aborts stale multipart uploads.
- Downloads are streamed by the API from MinIO with HTTP `Range` support (resume for `hibiscus pull`).

### Server-Sent Events
- SSE endpoints (run events, live metrics, live logs, notifications) send `event: heartbeat` every
  **15 s**, every real event carries an `id:`, and the server honours `Last-Event-ID` to replay
  missed events (from Postgres `run_events` / `run_metrics`, or the log offset).
- Response headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`,
  `X-Accel-Buffering: no`. Redis pub/sub feeds live events; Postgres is the replay source.

## Consequences

### Positive
- Works within Cloudflare limits; one mechanism for browser and CLI; resumable by part.
- MinIO stays private. Integrity end-to-end via per-part and whole-file sha256.

### Negative
- Upload/download bandwidth and connections consume API resources; uvicorn workers must be sized
  and timeouts tuned for streaming.
- Client-side hashing of multi-GB files costs CPU (Web Worker in browser).

### Follow-ups agents must honor
- A3: request body streaming (no full buffering in memory); reject chunks > 64 MiB with 413 + code;
  integration tests with testcontainers MinIO incl. resume after interrupted part.
- A4: SSE heartbeat 15 s and `Last-Event-ID` replay tested; live metric latency < 2 s (PLAN §6).
- A6: upload in a Web Worker with parallel parts (bounded) and resume; SSE reconnect logic.
- A9: CLI `hibiscus push` resumes from server part list; `hibiscus pull` uses `Range`.
- A8: proxy/uvicorn timeouts allow long streams; no response buffering on SSE paths.

## Rejected alternatives

- **Presigned URLs directly to MinIO:** requires exposing MinIO publicly.
- **Single large request upload:** breaks the 100 MB limit and cannot resume.
- **WebSockets for live data:** SSE is simpler, one-directional, and replays via `Last-Event-ID`.

## Related

- ADR-0004 (storage), ADR-0008 (Cloudflare), ADR-0002 (run events)
- `api/openapi.yaml` (uploads, SSE endpoints), `docs/spec/run-lifecycle.md`, `docs/spec/log-parsing.md`
