#!/usr/bin/env bash
# Report (or refresh) the digests of every third-party image pinned in deploy/ (SEC-infra-3).
# Images are referenced as `name:tag@sha256:<digest>`; the tag is for humans, the digest is what
# Docker pulls, so a re-pushed tag can never change what we run. Refreshing is a deliberate act:
#
#   deploy/scripts/pin-images.sh            # list pinned vs. current registry digest of each tag
#   deploy/scripts/pin-images.sh --write    # rewrite the pins to the current digests (review the diff!)
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WRITE="${1:-}"
FILES=(
  "$DEPLOY_DIR/docker-compose.yml"
  "$DEPLOY_DIR/docker/api.Dockerfile"
  "$DEPLOY_DIR/docker/web.Dockerfile"
  "$DEPLOY_DIR/docker/worker.Dockerfile"
  "$DEPLOY_DIR/backup/minio-mirror.sh"
)

mapfile -t refs < <(grep -ohE '[a-z0-9./_-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}' "${FILES[@]}" | sed 's/^-*//' | sort -u)
stale=0
for ref in "${refs[@]}"; do
  tag="${ref%@*}"
  pinned="${ref#*@}"
  current="$(docker buildx imagetools inspect "$tag" --format '{{json .Manifest.Digest}}' | tr -d '"')"
  if [[ "$current" == "$pinned" ]]; then
    echo "ok     $tag"
    continue
  fi
  stale=1
  echo "moved  $tag  pinned=${pinned:7:12}  registry=${current:7:12}"
  if [[ "$WRITE" == "--write" ]]; then
    sed -i "s|${tag}@${pinned}|${tag}@${current}|g" "${FILES[@]}"
  fi
done
if [[ $stale -eq 1 && "$WRITE" != "--write" ]]; then
  echo "some tags moved at the registry; re-run with --write after reviewing the release notes" >&2
fi
