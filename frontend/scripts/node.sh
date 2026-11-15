#!/usr/bin/env bash
# Run Node tooling for frontend/ inside a pinned Node container (the GPU host has no node/npm).
# Usage: frontend/scripts/node.sh pnpm install --frozen-lockfile
#        frontend/scripts/node.sh pnpm test
# Notes:
#  * --network host: the default bridge network on this host has no working DNS. The test/build
#    scripts start no server; never bind ports 8000/18000 (public via Cloudflare Tunnel). The
#    dev/preview scripts use 127.0.0.1:18100/18101.
#  * The repo root is mounted at /w so `../api/openapi.yaml` resolves for `pnpm gen:api`.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo="$(cd "$here/.." && pwd)"
cache="${HIBISCUS_NODE_CACHE:-$HOME/.cache/hibiscus-node}"
mkdir -p "$cache"
if [ "$#" -gt 0 ] && [ "$1" = "pnpm" ]; then shift; set -- corepack pnpm@9.15.0 "$@"; fi
tty_flag=()
if [ -t 0 ] && [ -t 1 ]; then tty_flag=(-it); fi
exec docker run --rm "${tty_flag[@]}" --network host \
  -u "$(id -u):$(id -g)" \
  -e HOME=/cache -e COREPACK_HOME=/cache/corepack -e COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
  -e npm_config_store_dir=/cache/pnpm-store -e CI=true \
  -v "$repo":/w -v "$cache":/cache -w /w/frontend \
  node:22.12-bookworm "$@"
