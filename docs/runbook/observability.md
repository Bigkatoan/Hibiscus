# Observability

| Component | Where | Notes |
|---|---|---|
| Grafana | `127.0.0.1:13000` (SSH tunnel) | folder **Hibiscus**: "Hibiscus overview", "Hibiscus logs"; admin from `GRAFANA_ADMIN_*`; no anonymous access, no plugin downloads |
| Prometheus | internal `prometheus:9090` (dev: `127.0.0.1:18102`) | 30 d retention, rules in `deploy/observability/prometheus/rules/` |
| Loki | internal `loki:3100` | 30 d retention, filesystem store |
| Alloy | reads `/var/lib/docker/containers/*/*-json.log` read-only | keeps only compose projects `hibiscus*`; no Docker socket |
| postgres-exporter | `hibiscus_monitor` role, aggregate SQL only | queue depth, run/job states, GPU node heartbeats |
| gpu-exporter | nvidia-smi based | utilisation, VRAM, temperature, power for both GPUs |

Dashboards are generated: edit `deploy/scripts/gen_dashboards.py`, run it, commit the JSON
(CI and pre-commit fail on drift). All PromQL in the dashboards is executed against a live
Prometheus by `deploy/tests/test_stack_smoke.py`.

## Metric contract (what the application must expose)

Infrastructure metrics work as-is. The API and worker panels expect these names — implementers
(A2 API middleware, A4 workers) please match them or tell the integrator:

| Metric | Type | Labels | Producer |
|---|---|---|---|
| `hibiscus_http_requests_total` | counter | `method`, `route` (template, e.g. `/api/v1/runs/{run_id}`), `status` | API |
| `hibiscus_http_request_duration_seconds` | histogram | `method`, `route` | API |
| worker `/metrics` on port `9108` (`HIBISCUS_METRICS_PORT`, 0 disables) | — | — | each worker (scraped as job `workers`), `worker/core/metrics.py` |
| `hibiscus_worker_info` | gauge (=1) | `worker_kind`, `gpu_id`, `version` | workers |
| `hibiscus_worker_jobs_claimed_total` / `_succeeded_total` / `_failed_total` | counter | `kind` (job kind, or `train_run`) | workers |
| `hibiscus_worker_lease_heartbeats_total` | counter | `result` (`ok`, `lost`) | workers |
| `hibiscus_worker_run_active`, `hibiscus_worker_run_current_step`, `hibiscus_worker_run_total_steps` | gauge | — | GPU workers |
| `hibiscus_worker_gpu_utilization_percent`, `_gpu_memory_used_bytes`, `_gpu_memory_total_bytes`, `_gpu_temperature_celsius`, `_gpu_power_watts` | gauge (NVML, read at scrape time) | `gpu_id` | GPU workers with NVML |

From Postgres (no app code needed): `hibiscus_run_queue_queued`, `hibiscus_run_queue_active`,
`hibiscus_run_queue_oldest_queued_seconds`, `hibiscus_runs_runs{status}`,
`hibiscus_jobs_jobs{kind,resource,status}`, `hibiscus_job_queue_queued{resource}`,
`hibiscus_gpu_node_online{node}`, `hibiscus_gpu_node_heartbeat_age_seconds{node,status}`,
`hibiscus_uploads_sessions{status}`. Before the migrations exist these queries log errors in the
Postgres log (relation does not exist); that is expected.

From nvidia_gpu_exporter: `nvidia_smi_utilization_gpu_ratio`, `nvidia_smi_memory_used_bytes`,
`nvidia_smi_memory_total_bytes`, `nvidia_smi_temperature_gpu`, `nvidia_smi_power_draw_watts`
(labels `uuid`, `name`). Not exercised in tests (no GPU access during the build phase) — verify
once on the box: `docker compose --project-directory deploy exec prometheus wget -qO- 'http://gpu-exporter:9835/metrics' | grep nvidia_smi_temperature`.

## Logs

Application logs are JSON (CONTRIBUTING §6). Alloy lifts `level` to a label and `request_id`,
`run_id`, `workspace_id` to Loki structured metadata, so in Grafana Explore:

```
{project="hibiscus", service="api"} | request_id="<id from X-Request-Id>"
{project="hibiscus", service=~"worker-.*"} | run_id="<run uuid>"
{project="hibiscus"} | level=~"error|critical"
```

Docker's json-file driver keeps 5 × 50 MB per container regardless of Loki.

## Alerts

There is no Alertmanager in v1; alerts are visible in Prometheus `/alerts` and the
"Firing alerts" stat on the overview dashboard. Each alert links a playbook in
[incidents.md](incidents.md). Adding notification delivery later: Grafana alerting contact point
or Alertmanager → the same Email Worker / a Discord webhook.
