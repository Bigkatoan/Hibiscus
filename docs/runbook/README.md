# Hibiscus operations runbook (owner: A8 DevOps/SRE)

Single GPU host, Docker Compose, public access only through the existing remotely-managed
Cloudflare Tunnel. Everything below assumes the repository is checked out on the GPU box and
commands run from the repo root.

| Topic | Page |
|---|---|
| First install, host prerequisites, tunnel origin | [install.md](install.md) |
| Upgrades, LeRobot bumps, rollbacks | [upgrade.md](upgrade.md) |
| Postgres backups, MinIO versioning/mirror, restore drills | [backup-restore.md](backup-restore.md) |
| Secrets inventory and rotation | [secrets.md](secrets.md) |
| GPU workers: mapping, drain, adding a GPU, P40 specifics | [gpu.md](gpu.md) |
| Dashboards, alerts, logs, metric contract | [observability.md](observability.md) |
| Cloudflare WAF / rate limits / Turnstile / Access | [cloudflare.md](cloudflare.md) |
| Email (Cloudflare Email Service Worker, SPF/DKIM/DMARC) | [email.md](email.md) |
| Incident playbooks (one per alert) | [incidents.md](incidents.md) |

## Facts that never change without an ADR

* Public URL `https://robot.example.com` → Cloudflare Tunnel (host systemd `cloudflared`,
  token-based, managed in the dashboard) → **`http://localhost:18000`** → `proxy` container.
* **Host port 8000 belongs to LeLab** (no auth, drives robot hardware). Hibiscus never binds it.
  `make config` / CI fail if any compose service would.
* Only loopback ports are published: `127.0.0.1:18000` (proxy) and `127.0.0.1:13000` (Grafana).
  The dev stack uses `127.0.0.1:18100-18106` under project `hibiscus-dev`.
* Postgres, Redis, MinIO, Prometheus, Loki and the API container are on `internal` Docker
  networks only. `/metrics` and `/readyz` answer 404 through the proxy.
* Nobody reads or copies `~/.cloudflared`; the tunnel token never enters this repository.

## Daily cheat sheet

```bash
make ps                       # status + health of every service
make logs SERVICE=api         # follow one service
make up                       # (re)start everything, waits for healthchecks
make restart                  # recreate api + proxy after editing deploy/.env
make backup-now               # immediate pg_dump into $HIBISCUS_BACKUP_DIR
ssh -L 13000:127.0.0.1:13000 gpu-box   # then open http://127.0.0.1:13000 (Grafana)
```
