# Incident playbooks

First three commands for any incident:

```bash
make ps                                   # which container is unhealthy / restarting
make logs SERVICE=<svc>                   # or Grafana → Hibiscus logs
curl -fsS http://127.0.0.1:18000/healthz  # origin up?
```

## site-down — robot.example.com unreachable
1. Origin: `curl http://127.0.0.1:18000/healthz`. If OK the problem is the tunnel/edge:
   `systemctl status cloudflared` (read-only check; do not edit its config), Cloudflare status
   page, Zero Trust → Tunnels shows the connector as healthy? Public hostname still →
   `http://localhost:18000`?
2. If the origin fails: `make ps`; `proxy` unhealthy → `make logs SERVICE=proxy`;
   API down → see [target-down](#target-down).
3. 1015/1020 errors at the edge = WAF/rate-limit rule; check Security → Events, adjust
   `edge.json`, `cf_edge.py apply`.

## target-down
Alert `HibiscusTargetDown{job=...}`. `make logs SERVICE=<job>`; restart once
(`docker compose --project-directory deploy up -d <svc>`). API: if `migrate` failed, the API
never starts — read `make logs SERVICE=migrate`, fix, `make up`. Loki/Alloy down only loses
log shipping (json logs remain on disk).

## postgres-down
`make logs SERVICE=postgres`. Disk full → [disk-full](#disk-full). Corruption: stop app
services, restore the last dump ([backup-restore.md](backup-restore.md#in-place-restore)); data
checksums are enabled (`--data-checksums`) so corruption is reported, not silently served.

## worker-down
`HibiscusWorkerDown` / `HibiscusGpuNodeHeartbeatStale` / `HibiscusJobQueueStuck`.
1. `make logs SERVICE=worker-cuda0` (or cuda1/cpu). OOM-killed (`docker inspect -f '{{.State.OOMKilled}}'`)?
   Raise `HIBISCUS_WORKER_GPU_MEMORY` or lower `num_workers`/batch for that run.
2. `nvidia-smi` on the host: Xid errors / fallen-off-the-bus → reboot needed; drain the GPU
   first ([gpu.md](gpu.md#drain-a-gpu)).
3. The run whose lease expired is re-queued once by the reaper and resumes from
   `checkpoints/last` (ADR-0002); nothing to do manually unless it failed twice.

## queue-stuck
`HibiscusRunQueueStuck`: runs queued, nothing running for 15 min.
* Both GPU nodes `draining`/`disabled`? (admin UI → GPUs).
* Queued runs need bf16 but only the P40 is online? (the scheduler should force fp32; check run events).
* Workers healthy but not claiming → worker logs, DB connectivity, `hibiscus_gpu_node_heartbeat_age_seconds`.

## api-errors / api-latency
`HibiscusApiErrorRate` (> 5 % 5xx) / `HibiscusApiLatencyP95` (> 200 ms). Grafana overview →
"Top routes by 5xx / p95". Logs: `{project="hibiscus",service="api"} | level="error"` and follow a
`request_id`. Postgres slow queries are logged (> 500 ms) in `make logs SERVICE=postgres`.
Under attack: Security → Events in Cloudflare; tighten `hibiscus_rl_*` or enable `allowed_countries`.

## gpu-hot
`HibiscusGpuTemperatureHigh` (> 85 °C for 5 min). P40 is passively cooled: check case fans/airflow.
Pause the run on that GPU (UI, `mode=next_checkpoint`) if it keeps rising; the driver throttles
near 90 °C and shuts down beyond.

## disk-full
`HibiscusMinioDiskLow` or Postgres write errors. `df -h`; `docker system df`.
Free space safely: old images `docker image prune` (keep the current and previous tag),
expired uploads are lifecycle-managed, dataset cache is LRU (`HIBISCUS_DATASET_CACHE_MAX_BYTES`),
non-current MinIO versions expire after 30 d (shorten temporarily via `.env` +
`docker compose ... up -d minio-init`). Never delete files under the MinIO volume by hand.

## backup-failing
`backup` container unhealthy (no dump for 26 h): `make logs SERVICE=backup`; usual causes are a
full or unmounted `HIBISCUS_BACKUP_DIR` or a changed DB password. Fix, then `make backup-now`.

## security-incident (suspected compromise)
1. Cut public access: Cloudflare Zero Trust → Tunnels → disable the public hostname (or stop
   `proxy`: `docker compose --project-directory deploy stop proxy`). LeLab on :8000 is unaffected.
2. Preserve evidence: `docker compose ... logs > incident-$(date +%F).log`; `audit_events` table;
   Cloudflare Security → Events export.
3. Rotate secrets ([secrets.md](secrets.md)), revoke all sessions/PATs (admin UI), reset admin 2FA.
4. Hand over to A11's checklist in `docs/security/`.
