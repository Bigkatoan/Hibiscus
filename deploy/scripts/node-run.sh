#!/usr/bin/env bash
# Run a Node tool in DIR, with the host's node if available, otherwise in a node:22.12 container
# (the GPU box has no node). Used by .pre-commit-config.yaml and the Makefile.
#   deploy/scripts/node-run.sh frontend pnpm lint
#   deploy/scripts/node-run.sh deploy/cloudflare/email-worker npm test
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIR="${1:?usage: node-run.sh DIR CMD...}"
shift
[[ -f "$ROOT/$DIR/package.json" ]] || { echo "node-run: $DIR has no package.json yet, skipping"; exit 0; }
PNPM_VERSION="${PNPM_VERSION:-9.15.0}"

if command -v node >/dev/null 2>&1; then
  cd "$ROOT/$DIR"
  exec "$@"
fi

exec docker run --rm --network "${NODE_NETWORK:-host}" -u "$(id -u):$(id -g)" -e HOME=/tmp -e CI=true \
  -v "$ROOT:/repo" -w "/repo/$DIR" "${NODE_IMAGE:-node:22.12-bookworm}" \
  sh -c 'if [ "$1" = pnpm ]; then npm i -g --prefix /tmp/pnpm "pnpm@'"$PNPM_VERSION"'" >/dev/null 2>&1; export PATH=/tmp/pnpm/bin:$PATH; fi; exec "$@"' \
  node-run "$@"
