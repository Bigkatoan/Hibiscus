# Install

## 1. Host prerequisites

| Item | Required | Check |
|---|---|---|
| Docker Engine ≥ 27, Compose v2.24+ (uses `!override`/`!reset`) | yes | `docker compose version` |
| NVIDIA driver ≥ 580 (CUDA 13.2 wheels for the 3060 image) + `nvidia-container-toolkit` | yes | `cat /proc/driver/nvidia/version`, `docker info \| grep -i runtimes` |
| `uv` (for `make config`, tests, the edge script) | yes | `uv --version` |
| Free disk on Docker's data-root: ~40 GB images + datasets cache (≤ 150 GB) + MinIO | yes | `df -h /var/lib/docker` |
| Node | no | Node tooling runs in `node:22.12-bookworm` containers |

The worker images are large: `worker-gpu` ≈ 12 GB, `worker-gpu-pascal` ≈ 13 GB,
`worker-cpu` ≈ 4 GB.

## 2. Known host quirk: no egress from bridge containers

On the GPU box (2026-11-15) containers on Docker bridge networks get **no DNS and no outbound
traffic** (`docker run --rm python:3.12-slim python -c "import socket; socket.gethostbyname('pypi.org')"`
fails), while `--network host` works. Consequences and workarounds:

* **Builds**: set `HIBISCUS_BUILD_NETWORK=host` in `deploy/.env` (compose `build.network`) and
  export it for `deploy/scripts/build-images.sh`. `BUILDX_BUILDER=default` (set by the Makefile)
  keeps builds on the daemon's BuildKit instead of a docker-container builder.
* **Runtime** (must be fixed before go-live): the API needs egress to the Email Worker and
  Turnstile, the workers to the Hugging Face Hub. Likely cause is the host firewall dropping
  forwarded traffic from `docker0`/`br-*` (UFW `DEFAULT_FORWARD_POLICY="DROP"` or missing
  MASQUERADE). Fix on the host as root, e.g. for UFW set `DEFAULT_FORWARD_POLICY="ACCEPT"` in
  `/etc/default/ufw` and `ufw reload`, or add `iptables -I DOCKER-USER -i br-+ -j ACCEPT`.
  Verify with the command above. The internal networks (`data`, `obs`, `app`) stay isolated
  regardless — they are `internal: true`.

## 3. Configure

```bash
make env                                  # deploy/.env from .env.example (mode 600)
make secrets                              # paste the generated values into deploy/.env
$EDITOR deploy/.env                       # HIBISCUS_BACKUP_DIR (other disk!), email, Turnstile
make config                               # renders compose + enforces the exposure policy
```

`deploy/.env` is git-ignored. Never commit it, never paste it into tickets.

## 4. Build and start

```bash
make build            # api, web (SPA + Caddy), worker-gpu, worker-gpu-pascal, worker-cpu
make up               # waits until every healthcheck is green
make ps
curl -fsS http://127.0.0.1:18000/healthz           # {"status":"ok"}
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18000/metrics   # 404 (by design)
```

First start: `postgres/initdb/10-hibiscus.sh` creates the app role, the monitor role and the
`monitoring` schema; `minio-init` creates buckets, versioning, lifecycle and the app user;
`migrate` runs `alembic upgrade head`. Then bootstrap the first platform admin
(CONTRACT_NOTES §4.2):

```bash
docker compose --project-directory deploy exec api python -m app.admin.bootstrap --email you@example.com
```

## 5. Point the tunnel at Hibiscus (user action, dashboard only)

The tunnel is remotely managed: Cloudflare Zero Trust → Networks → Tunnels → (tunnel) →
Public Hostname `robot.example.com` → Service `http://localhost:18000`. Do **not** keep it on
`localhost:8000` (that is LeLab). No local `cloudflared` config file exists or is needed; the
systemd service is not touched by this repo.

Then apply the edge rules ([cloudflare.md](cloudflare.md)) and check from outside:

```bash
curl -fsS https://robot.example.com/healthz
curl -s -o /dev/null -w '%{http_code}\n' https://robot.example.com/metrics   # 403 (edge) or 404
```

## 6. Development stack

```bash
cp deploy/.env.example deploy/.env.dev && $EDITOR deploy/.env.dev
docker compose -p hibiscus-dev --project-directory deploy -f deploy/docker-compose.yml \
  -f deploy/compose.dev.yml --env-file deploy/.env.dev up -d --wait
# proxy http://127.0.0.1:18100, Grafana :18101, Prometheus :18102, MinIO console :18103,
# Postgres :18104, Redis :18105, MinIO S3 :18106. GPU workers: add --profile gpu.
```
