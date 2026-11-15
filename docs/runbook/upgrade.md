# Upgrade and rollback

## Routine upgrade (application code)

```bash
git pull --ff-only
make config                       # policy check on the new compose files
make backup-now                   # always take a fresh dump before migrations
HIBISCUS_IMAGE_TAG=$(git rev-parse --short HEAD) make build
sed -i "s/^HIBISCUS_IMAGE_TAG=.*/HIBISCUS_IMAGE_TAG=$(git rev-parse --short HEAD)/" deploy/.env
make up                           # migrate runs first; api waits for it
```

Workers stop gracefully: `stop_grace_period: 120s`, SIGTERM → the worker pauses/hands back its
lease (run-lifecycle §8); runs resume from `checkpoints/last` on the new container. To avoid
interrupting long runs, drain first ([gpu.md](gpu.md#drain-a-gpu)).

Keep the previous image tag in `deploy/.env` history; images are tagged per commit so rollback is
a tag change.

## Rollback

1. `HIBISCUS_IMAGE_TAG=<previous>` in `deploy/.env`, `make up`.
2. If the failed release ran a migration that is not backward compatible: stop app services and
   restore the pre-upgrade dump ([backup-restore.md](backup-restore.md#in-place-restore)).
   Alembic downgrades are not relied upon.

## Infrastructure image bumps

Pinned in `deploy/docker-compose.yml` (overridable via `HIBISCUS_*_IMAGE` variables): Postgres
16.16, Redis 7.4.12, MinIO (pgsty community build — upstream stopped publishing images in 2025),
Caddy 2.11.9, Prometheus 3.16.0, Grafana 13.2.6, Loki 3.7.10, Alloy 1.22.0, postgres-exporter
0.20.1, nvidia_gpu_exporter 1.18.0. Bump one at a time, run `make test-smoke` (full stack with
stub app) and `make test-deploy`, then roll out. Postgres **major** upgrades need
dump/restore into a new volume (never switch the image on an existing 16 data dir).

## LeRobot / torch bump (ADR-0003)

`deploy/docker/worker.Dockerfile` pins LeRobot by upstream commit (`LEROBOT_GIT_REF`; 0.7.1 is
not on PyPI) and asserts the reported version; torch is pinned per variant in
`deploy/scripts/build-images.sh` and the `x-worker` build args in `docker-compose.yml`:

| Variant | Torch | Why |
|---|---|---|
| worker-gpu (cuda0, RTX 3060) | 2.15.0 (PyPI, CUDA 13.2) | same as the LeLab reference venv |
| worker-gpu-pascal (cuda1, P40) | 2.14.1+cu126 | newest torch with sm_60/61 kernels; 2.15 wheels start at sm_75 |
| worker-cpu | 2.15.0+cpu | validation / import, no GPU |

A bump requires: an ADR note, rebuilding all three variants, `torch.cuda.get_arch_list()` still
containing `sm_60` for the Pascal image, and a green golden E2E on **both** GPUs (PLAN §6).
