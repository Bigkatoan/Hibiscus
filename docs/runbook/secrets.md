# Secrets

All secrets live in `deploy/.env` (mode 600, git-ignored; template `deploy/.env.example`,
generator `make secrets`). Compose refuses to start when a required one is missing. Each
container receives only the variables it needs (explicit `environment:` maps, no `env_file`).

| Secret | Used by | Rotation |
|---|---|---|
| `POSTGRES_SUPERUSER_PASSWORD` | postgres (first init only) | `ALTER ROLE postgres PASSWORD ...` via `docker compose exec postgres psql -U postgres`, then update `.env` |
| `HIBISCUS_DB_PASSWORD` | api, migrate, workers, backup | `ALTER ROLE hibiscus PASSWORD '<new>'`; update `.env`; `make up` (recreates consumers) |
| `HIBISCUS_DB_MONITOR_PASSWORD` | postgres-exporter | `ALTER ROLE hibiscus_monitor PASSWORD '<new>'`; `.env`; `make up` |
| `HIBISCUS_REDIS_PASSWORD` | redis, api, workers | update `.env`, `make up` (redis restarts; only volatile data) |
| `MINIO_ROOT_PASSWORD` | minio, minio-init | update `.env`, `docker compose up -d minio minio-init` (root creds are env-defined) |
| `HIBISCUS_S3_SECRET_KEY` | api, workers | update `.env`, `make up` — `minio-init` re-runs `mc admin user add` (upsert) before the app starts |
| `HIBISCUS_DATA_KEY` | api (AES-256-GCM of TOTP + user secrets) | **not** a plain swap: needs the API's re-encryption procedure (A2); never lose the old key — store it in the password manager |
| `HIBISCUS_JWT_PRIVATE_KEY` | api, migrate (Ed25519 PEM, one line with `\n` in double quotes) | new key from `make secrets`; move the old **public** key into `HIBISCUS_JWT_PREVIOUS_PUBLIC_KEYS` for one access-token lifetime (15 min), then drop it |
| `HIBISCUS_CURSOR_SECRET` | api, migrate (pagination cursors) | update `.env`, `make restart` (open list cursors become invalid; clients restart from page 1) |
| `HIBISCUS_BACKUP_PASSPHRASE` | backup, minio-mirror.sh, restore.sh (gpg AES-256) | see docs/runbook/backup-restore.md "Encryption key"; keep the old value until old dumps expire; a copy MUST live off-host |
| `HIBISCUS_EMAIL_WORKER_SECRET` | api ↔ Email Worker | zero-downtime procedure in `deploy/cloudflare/email-worker/README.md` |
| `HIBISCUS_TURNSTILE_SECRET_KEY` | api | Cloudflare dashboard → Turnstile → rotate secret; update `.env`; `make restart` |
| `GRAFANA_ADMIN_PASSWORD` | grafana (first start) | change in Grafana UI (env only seeds a new volume) |
| Cloudflare API token | `cf_edge.py` (operator shell only) | never stored; create a scoped token per session and revoke it after |
| Tunnel token | host `cloudflared` systemd service | **not handled by this repo.** Rotate in Zero Trust → Tunnels → (tunnel) → Refresh token, then `sudo cloudflared service install <new token>` on the host |

Rules: no secret in git, compose files, images or logs (the email Worker and API redact);
`deploy/.env` is not part of backups by design — keep a copy of it in the team password manager.
After any suspected leak rotate the affected secret and the PATs/sessions via the admin UI.
