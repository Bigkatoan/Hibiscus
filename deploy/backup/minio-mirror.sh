#!/usr/bin/env bash
# Off-volume, ENCRYPTED copy of the MinIO buckets (datasets + artifacts; uploads are transient).
# MinIO versioning protects against deletes/overwrites, NOT against losing the disk, so run this
# weekly (systemd timer in docs/runbook/backup-restore.md) towards a different disk / NAS.
#
#   deploy/backup/minio-mirror.sh /mnt/backup/hibiscus-minio [--remove]
#
# Every object is streamed out of MinIO and written as <bucket>/<key>.gpg, encrypted with
# HIBISCUS_BACKUP_PASSPHRASE (gpg AES-256, see crypt.sh; SEC-infra-2): the destination never holds
# plaintext. Incremental: an object is re-encrypted only when its ETag changed (the ETag is stored
# as a keyed hash, <key>.gpg.etag, so it does not leak the MD5 of the content).
# Restore: deploy/backup/decrypt-tree.sh, then `mc mirror` back (docs/runbook/backup-restore.md).
#
# Runs a throwaway container from the stack's Postgres image (bash + gpg) on the internal `data`
# network, with the `mc` binary taken from the pinned mc image, and the app credentials from
# deploy/.env (read-only use of MinIO).
#   --remove  also delete files in the destination whose object no longer exists in MinIO
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:?usage: $0 DEST_DIR [--remove]}"
REMOVE="${2:-}"
PROJECT="${COMPOSE_PROJECT_NAME:-hibiscus}"
ENV_FILE="${HIBISCUS_ENV_FILE:-$DEPLOY_DIR/.env}"
MC_IMAGE="${HIBISCUS_MC_IMAGE:-pgsty/mc:RELEASE.2026-11-12T00-00-00Z@sha256:b532278b7a3747dbab6fe45eebb40a653efa704e6758e24e9d9ec54fc96c1800}"
RUNNER_IMAGE="${HIBISCUS_POSTGRES_IMAGE:-postgres:16.16-trixie@sha256:dd2bf3ce2dc83a81674cf7f217fcfd8a5009a4b325dda5b843bfee82a06cff6f}"
NETWORK="${HIBISCUS_MIRROR_NETWORK:-${PROJECT}_data}"

get_env() {
  local v
  v="$(grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2-)"
  v="${v%\"}"
  printf '%s' "${v#\"}"
}
ACCESS_KEY="${HIBISCUS_S3_ACCESS_KEY:-$(get_env HIBISCUS_S3_ACCESS_KEY)}"
SECRET_KEY="${HIBISCUS_S3_SECRET_KEY:-$(get_env HIBISCUS_S3_SECRET_KEY)}"
HIBISCUS_BACKUP_PASSPHRASE="${HIBISCUS_BACKUP_PASSPHRASE:-$(get_env HIBISCUS_BACKUP_PASSPHRASE)}"
[[ -n "$ACCESS_KEY" && -n "$SECRET_KEY" ]] || { echo "S3 credentials missing in $ENV_FILE" >&2; exit 1; }
# shellcheck source=SCRIPTDIR/crypt.sh
source "$DEPLOY_DIR/backup/crypt.sh"
export HIBISCUS_BACKUP_PASSPHRASE
backup_require_passphrase

mkdir -p "$DEST"
tools="$(mktemp -d "${TMPDIR:-/tmp}/hibiscus-mc.XXXXXX")"
cid=""
cleanup() { [[ -z "$cid" ]] || docker rm -f "$cid" >/dev/null 2>&1 || true; rm -rf "$tools"; }
trap cleanup EXIT
# The mc image has no gpg; copy its static mc binary into the runner instead.
cid="$(docker create "$MC_IMAGE")"
docker cp "$cid:/usr/bin/mc" "$tools/mc" >/dev/null
docker rm "$cid" >/dev/null
cid=""
chmod 0755 "$tools/mc"

# Credentials and passphrase are passed by name (-e VAR) so they never appear in the process list.
export MC_HOST_lt="http://${ACCESS_KEY}:${SECRET_KEY}@minio:9000"
docker run --rm --network "$NETWORK" \
  -e MC_HOST_lt -e HIBISCUS_BACKUP_PASSPHRASE -e MIRROR_REMOVE="$REMOVE" \
  -u "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$tools/mc:/usr/local/bin/mc:ro" \
  -v "$DEPLOY_DIR/backup:/backup:ro" \
  -v "$(realpath "$DEST"):/mirror" \
  --entrypoint /bin/bash "$RUNNER_IMAGE" /backup/minio-mirror-worker.sh hibiscus-datasets hibiscus-artifacts
date -u +%FT%TZ > "$DEST/last-mirror"
echo "minio mirror ok (encrypted) -> $DEST"
