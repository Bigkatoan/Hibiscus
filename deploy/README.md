# deploy/ (owner: A8 DevOps/SRE)

Docker Compose deployment of Hibiscus on the GPU box. Operator docs: [`docs/runbook/`](../docs/runbook/README.md).

| Item | Value |
|---|---|
| Public URL | https://robot.example.com (remotely-managed Cloudflare Tunnel, `cloudflared` = host systemd service, not managed here) |
| Tunnel origin (set by the user in the Cloudflare dashboard) | `http://localhost:18000` |
| Hibiscus public entrypoint | `proxy` (Caddy + SPA) published as `127.0.0.1:18000`, plain HTTP |
| Forbidden host port | **8000** (LeLab backend) — enforced by `scripts/check_compose.py` |
| Other published ports | Grafana `127.0.0.1:13000` only (dev stack: `127.0.0.1:18100-18106`) |
| API | `api:8000` on internal networks only |
| GPU workers | `worker-cuda0` (`device_ids: ["0"]`, RTX 3060, torch 2.15/cu132), `worker-cuda1` (`["1"]`, Tesla P40, torch 2.14.1/cu126, fp32), shared `/cache` + `/scratch`, `stop_grace_period: 120s` |
| CPU worker | `worker-cpu` (`python -m validate`: validate / HF import / merge) |
| Images | every pulled image and base image pinned as `tag@sha256:...` (refresh: `scripts/pin-images.sh`) |
| Env contract | compose passes only names the apps read (`tests/test_env_contract.py`) |

## Layout

```
docker-compose.yml          production stack (project "hibiscus")
compose.dev.yml             dev overlay (project "hibiscus-dev", ports 18100-18106, GPU workers behind profile "gpu")
.env.example                every variable compose reads; copy to .env (git-ignored)
docker/                     api / web (Caddy+SPA) / worker (gpu | gpu-pascal | cpu) Dockerfiles + per-Dockerfile .dockerignore
caddy/Caddyfile             reverse proxy: routing, body limits, SSE, CF-Connecting-IP trust, security headers
postgres/initdb/            app role, monitor role, aggregate-only monitoring functions
minio/                      bucket/versioning/lifecycle/app-user bootstrap + least-privilege policy
backup/                     nightly encrypted pg_dump loop, healthcheck, restore.sh, encrypted minio-mirror.sh, decrypt-tree.sh
observability/              prometheus (+rules), loki, alloy, grafana provisioning + generated dashboards, postgres-exporter queries
cloudflare/email-worker/    TypeScript Worker owning the send_email binding (HMAC-signed requests from the API)
cloudflare/edge/            WAF / rate limit / cache rules, Turnstile, Access as code (cf_edge.py + edge.json)
scripts/                    build-images.sh, check_compose.py, gen_dashboards.py, gen-secrets.sh, node-run.sh
tests/                      pytest: compose policy, postgres+exporter+backup/restore, configs, edge client, full-stack smoke (stubs/)
```

## Quick start

```bash
make env && make secrets        # then edit deploy/.env
make build && make up
make test-deploy                # fast + docker-backed tests (~30 s)
make test-smoke                 # full stack with stub API/SPA (~2 min warm)
```

Never read, copy or commit anything from `~/.cloudflared`; the tunnel token stays on the host.
