#!/usr/bin/env bash
# pip-audit every uv project that has a lock file (CI `audit` job and `make audit`).
#
#   tools/pip_audit.sh [project ...]        # default: backend worker cli deploy
#
# Input is `uv export` of the lock file (exact pins, no hashes), adjusted for what pip-audit rejects:
#   * colour: with FORCE_COLOR=1 (set in CI) uv colours the "# via" comments, so they no longer look
#     like comments and pip-audit fails with "Expected package name" -> export with --color never and
#     drop comment/blank lines (newer pip-audit rejects comment lines as well);
#   * direct URL requirements (`lerobot @ git+https://...@<sha>` in worker): pip-audit refuses
#     "URL requirements cannot be pinned to a specific package version". They are pinned to a commit
#     and are not on PyPI's advisory feed, so they are listed and skipped here (lerobot is tracked
#     by its pinned commit in worker/pyproject.toml);
#   * local version labels (`torchcodec==0.17.0+cpu` from the PyTorch CPU index) are "not found on
#     PyPI" (an error under --strict): the label is stripped so the same upstream release is audited.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Reviewed exceptions: "<project>:<vuln id>  # reason". Keep each one justified and re-check on bumps.
IGNORES=(
  # openapi-python-client is a dev-only code generator for cli/hibiscus/_generated (never installed
  # with the CLI). PYSEC-2026-4245 (fixed in 0.29.1) is code injection from a *malicious* OpenAPI
  # document; we only ever generate from our own api/openapi.yaml, and the generated code is
  # committed and reviewed. Pinned at 0.28.4 (its output still runs on Python 3.10, checked by the
  # CLI tests); remove this entry once we move to 0.29.1+.
  "cli:PYSEC-2026-4245"
)

projects=("$@")
[ ${#projects[@]} -gt 0 ] || projects=(backend worker cli deploy)

status=0
for p in "${projects[@]}"; do
  if [ ! -f "$ROOT/$p/uv.lock" ]; then
    echo "skip $p (no uv.lock)"
    continue
  fi
  echo "== $p"
  req="$TMP/$p-req.txt"
  uv export --color never --project "$ROOT/$p" --locked --no-hashes --no-emit-project \
    --format requirements-txt | grep -vE '^[[:space:]]*(#|$)' > "$TMP/$p-all.txt"
  grep -E '^[A-Za-z0-9._-]+(\[[^]]*\])? @ ' "$TMP/$p-all.txt" | sed 's/^/  not audited (direct URL): /' || true
  grep -vE '^[A-Za-z0-9._-]+(\[[^]]*\])? @ ' "$TMP/$p-all.txt" \
    | sed -E 's/^([A-Za-z0-9._-]+(\[[^]]*\])?==[^ ;+]+)\+[^ ;]+/\1/' > "$req" || true
  args=()
  for entry in "${IGNORES[@]}"; do
    if [ "${entry%%:*}" = "$p" ]; then
      args+=(--ignore-vuln "${entry#*:}")
    fi
  done
  uvx --python "$PYTHON_VERSION" pip-audit --progress-spinner off --strict --disable-pip --no-deps \
    "${args[@]}" -r "$req" || status=1
done
exit $status
