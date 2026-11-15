#!/usr/bin/env bash
# Golden-journey E2E (PLAN §6) against the REAL stack. Owner: A10 QC.
#
#   tests/e2e/golden_journey/run.sh            # up -> journey -> LeLab load check -> down -v
#   E2E_KEEP=1 tests/e2e/golden_journey/run.sh  # leave the stack running afterwards
#   E2E_BUILD=1 ...                             # (re)build api/web/worker-cpu/worker-gpu first
#   E2E_EMAIL_STUB=0 ...                        # skip the local Email Worker (wrangler dev)
#
# The stack is the documented one (deploy/docker-compose.yml + deploy/compose.dev.yml, secrets from
# deploy/scripts/gen-secrets.sh) plus compose.e2e.yml, which only moves the published ports and the
# public base URL. No configuration workaround overlay is applied any more (QC-e2e-01..03, 08-10).
#
# Requirements: docker (+ nvidia runtime for worker-cuda0/1), uv, the local image
# hibiscus-playwright:1.49.1 (mcr.microsoft.com/playwright/python:v1.49.1-noble), the golden
# archive and a LeLab venv. Ports: E2E_PORT_BASE..+6 (default 18150-18156, loopback only).
# Never uses 8000 / 18000. Secrets are generated into a throwaway dir and deleted on exit.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
DEPLOY="$ROOT/deploy"

: "${E2E_PROJECT:=hibiscus-e2e}"
: "${E2E_PORT_BASE:=18150}"
: "${E2E_TAG:=e2e}"
: "${E2E_ARCHIVE:=~/lelab/Picknplace_20261114_221710.rar}"
: "${E2E_LELAB_PY:=~/lelab/leLab/.venv/bin/python}"
: "${E2E_PLAYWRIGHT_IMAGE:=hibiscus-playwright:1.49.1}"
: "${E2E_OUT:=${TMPDIR:-/tmp}/hibiscus-e2e-$(date +%Y%m%d-%H%M%S)}"
: "${E2E_ADMIN_EMAIL:=qa-admin@example.com}"
: "${E2E_TRAIN_STEPS:=300}"
: "${E2E_RUN_TIMEOUT_S:=1500}"
: "${E2E_EMAIL_STUB:=1}"
: "${E2E_EMAIL_PORT:=8787}"
: "${E2E_NODE_IMAGE:=node:22.12-bookworm}"

if (( E2E_PORT_BASE < 18100 || E2E_PORT_BASE + 6 > 18199 )); then
  echo "E2E_PORT_BASE must keep every port inside 18100-18199" >&2; exit 2
fi

mkdir -p "$E2E_OUT"
SECRETS="$(mktemp -d "${TMPDIR:-/tmp}/hibiscus-e2e-secrets.XXXXXX")"
chmod 700 "$SECRETS"
ENVF="$SECRETS/env"

# --- throwaway env ------------------------------------------------------------------------------
grep -vE '^(POSTGRES_SUPERUSER_PASSWORD|HIBISCUS_DB_PASSWORD|HIBISCUS_DB_MONITOR_PASSWORD|HIBISCUS_REDIS_PASSWORD|MINIO_ROOT_PASSWORD|HIBISCUS_S3_SECRET_KEY|HIBISCUS_DATA_KEY|HIBISCUS_JWT_PRIVATE_KEY|HIBISCUS_CURSOR_SECRET|HIBISCUS_EMAIL_WORKER_SECRET|HIBISCUS_BACKUP_PASSPHRASE|GRAFANA_ADMIN_PASSWORD|HIBISCUS_IMAGE_TAG|HIBISCUS_BUILD_NETWORK|HIBISCUS_EMAIL_PROVIDER|HIBISCUS_EMAIL_WORKER_URL|HIBISCUS_BACKUP_DIR|HIBISCUS_ENV)=' \
  "$DEPLOY/.env.example" > "$ENVF"
"$DEPLOY/scripts/gen-secrets.sh" >> "$ENVF"
mkdir -p "$SECRETS/backups"
# shellcheck disable=SC2129
cat >> "$ENVF" <<EOF
HIBISCUS_ENV=dev
HIBISCUS_IMAGE_TAG=$E2E_TAG
HIBISCUS_BUILD_NETWORK=host
HIBISCUS_EMAIL_PROVIDER=$([[ "$E2E_EMAIL_STUB" == 1 ]] && echo cloudflare || echo none)
HIBISCUS_EMAIL_WORKER_URL=$([[ "$E2E_EMAIL_STUB" == 1 ]] && echo "http://email-worker:$E2E_EMAIL_PORT/send")
HIBISCUS_BACKUP_DIR=$SECRETS/backups
E2E_PORT_BASE=$E2E_PORT_BASE
E2E_PORT_GRAFANA=$((E2E_PORT_BASE + 1))
E2E_PORT_PROMETHEUS=$((E2E_PORT_BASE + 2))
E2E_PORT_MINIO_CONSOLE=$((E2E_PORT_BASE + 3))
E2E_PORT_POSTGRES=$((E2E_PORT_BASE + 4))
E2E_PORT_REDIS=$((E2E_PORT_BASE + 5))
E2E_PORT_MINIO_S3=$((E2E_PORT_BASE + 6))
HIBISCUS_DEV_EDGE_SUBNET=${E2E_EDGE_SUBNET:-172.31.230.0/24}
HIBISCUS_DEV_EDGE_GATEWAY=${E2E_EDGE_GATEWAY:-172.31.230.1}
HIBISCUS_DEV_APP_SUBNET=${E2E_APP_SUBNET:-172.31.231.0/24}
HIBISCUS_DEV_PROXY_APP_IP=${E2E_PROXY_APP_IP:-172.31.231.2}
HIBISCUS_DEV_API_APP_IP=${E2E_API_APP_IP:-172.31.231.10}
EOF

FILES=(-f "$DEPLOY/docker-compose.yml" -f "$DEPLOY/compose.dev.yml" -f "$HERE/compose.e2e.yml")
dc() { docker compose -p "$E2E_PROJECT" --project-directory "$DEPLOY" "${FILES[@]}" --env-file "$ENVF" "$@"; }
EMAIL_CT="$E2E_PROJECT-email-worker"

cleanup() {
  local rc=$?
  dc logs --no-color > "$E2E_OUT/compose.log" 2>&1 || true
  docker logs "$EMAIL_CT" > "$E2E_OUT/email-worker.log" 2>&1 || true
  if [[ "${E2E_KEEP:-0}" != 1 ]]; then docker rm -f "$EMAIL_CT" >/dev/null 2>&1 || true; rm -rf "${EMAIL_DIR:-}"; fi
  if [[ "${E2E_KEEP:-0}" != 1 ]]; then dc --profile gpu down -v --remove-orphans >/dev/null 2>&1 || true; fi
  if [[ "${E2E_KEEP:-0}" == 1 ]]; then
    echo "stack kept: env file $ENVF, admin credentials $E2E_OUT/keep-session.json (delete both after down -v)"
  else
    rm -rf "$SECRETS"
  fi
  echo "artifacts: $E2E_OUT (exit $rc)"
}
trap cleanup EXIT

if [[ "${E2E_BUILD:-0}" == 1 ]]; then
  for t in api web worker-cpu worker-gpu worker-gpu-pascal; do
    HIBISCUS_IMAGE_TAG="$E2E_TAG" HIBISCUS_BUILD_NETWORK=host BUILDX_BUILDER=default \
      "$DEPLOY/scripts/build-images.sh" "$t"
  done
fi

echo "== up ($E2E_PROJECT, proxy 127.0.0.1:$E2E_PORT_BASE, full stack incl. both GPU workers)"
# Documented start: `up -d --wait` (install.md §6) with the gpu profile, i.e. every service incl.
# worker-cuda0 (RTX 3060), worker-cuda1 (P40), gpu-exporter, observability and backup.
dc --profile gpu up -d --no-build --wait --wait-timeout 600
curl -fsS "http://127.0.0.1:$E2E_PORT_BASE/healthz"; echo
dc --profile gpu ps --format 'table {{.Service}}\t{{.Status}}' | tee "$E2E_OUT/compose-ps.txt"

if [[ "$E2E_EMAIL_STUB" == 1 ]]; then
  # The real Email Worker (deploy/cloudflare/email-worker) under `wrangler dev --local`; its
  # send_email binding is emulated by miniflare (writes the message to .wrangler/tmp/email).
  # It joins the stack's egress network as "email-worker", the URL the api was given above.
  echo "== email worker (wrangler dev) on ${E2E_PROJECT}_egress"
  EMAIL_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hibiscus-e2e-email.XXXXXX")"
  (cd "$DEPLOY/cloudflare/email-worker" && cp -r package.json package-lock.json src tsconfig.json wrangler.toml "$EMAIL_DIR/")
  printf 'HIBISCUS_EMAIL_HMAC_SECRET=%s\n' "$(grep -E '^HIBISCUS_EMAIL_WORKER_SECRET=' "$ENVF" | tail -1 | cut -d= -f2-)" > "$EMAIL_DIR/.dev.vars"
  docker run --rm --network host -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$EMAIL_DIR:/w" -w /w \
    "$E2E_NODE_IMAGE" npm ci --no-audit --no-fund --loglevel=error >/dev/null
  docker run -d --name "$EMAIL_CT" --network "${E2E_PROJECT}_egress" --network-alias email-worker \
    -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$EMAIL_DIR:/w" -w /w "$E2E_NODE_IMAGE" \
    npx wrangler dev --local --ip 0.0.0.0 --port "$E2E_EMAIL_PORT" >/dev/null
  for _ in $(seq 1 60); do
    dc exec -T api python -c "import urllib.request as u; u.urlopen('http://email-worker:$E2E_EMAIL_PORT/health', timeout=2)" \
      >/dev/null 2>&1 && break; sleep 2
  done
fi

echo "== bootstrap first admin"
LINK="$(dc exec -T api python -m app.admin.bootstrap --email "$E2E_ADMIN_EMAIL" --display-name 'QA Admin' | grep -Eo 'http[^ ]+reset-password#token=[A-Za-z0-9_-]+' | tail -1)"
[[ -n "$LINK" ]] || { echo "bootstrap printed no link" >&2; exit 1; }

echo "== journey (pytest + playwright in $E2E_PLAYWRIGHT_IMAGE)"
set +e
docker run --rm --network host --ipc host \
  -e E2E_BASE_URL="http://127.0.0.1:$E2E_PORT_BASE" -e E2E_BOOTSTRAP_LINK="$LINK" \
  -e E2E_ADMIN_EMAIL="$E2E_ADMIN_EMAIL" -e E2E_OUT=/out -e E2E_ARCHIVE="/golden/$(basename "$E2E_ARCHIVE")" \
  -e E2E_TRAIN_STEPS="$E2E_TRAIN_STEPS" -e E2E_RUN_TIMEOUT_S="$E2E_RUN_TIMEOUT_S" \
  -e E2E_EMAIL_STUB="$E2E_EMAIL_STUB" -e E2E_KEEP="${E2E_KEEP:-0}" -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
  -v "$ROOT:/repo:ro" -v "$E2E_OUT:/out" -v "$E2E_ARCHIVE:/golden/$(basename "$E2E_ARCHIVE"):ro" \
  "$E2E_PLAYWRIGHT_IMAGE" bash -c '
    set -e
    pip install -q --root-user-action=ignore -r /repo/tests/e2e/golden_journey/requirements.txt
    # no python3-venv in the image; the container is throwaway, so install the CLI system-wide
    pip install -q --root-user-action=ignore /repo/cli
    cd /repo/tests/e2e/golden_journey
    set +e
    python3 -m pytest -p no:cacheprovider -v -rA --junitxml=/out/junit.xml test_golden_journey.py
    rc=$?; chown -R '"$(id -u):$(id -g)"' /out; exit $rc'
PYTEST_RC=$?
set -e

echo "== worker / email evidence"
dc --profile gpu ps --format 'table {{.Service}}\t{{.Status}}' > "$E2E_OUT/compose-ps-end.txt" || true
for w in worker-cuda0 worker-cuda1 worker-cpu; do
  dc --profile gpu logs --no-color "$w" 2>/dev/null | grep -iE 'regist|gpu_id|cuda[01]|fp32|bf16|mixed_precision' | head -20 \
    > "$E2E_OUT/$w-registration.txt" || true
done
EMAIL_RC=0
if [[ "$E2E_EMAIL_STUB" == 1 ]]; then
  sleep 3
  docker logs "$EMAIL_CT" > "$E2E_OUT/email-worker.log" 2>&1 || true
  # test_17 requested a password reset for the admin: the Worker must have accepted the API's
  # signed request (202) and called its send_email binding for that recipient.
  if grep -q 'send_email binding called' "$E2E_OUT/email-worker.log" && grep -q "To: $E2E_ADMIN_EMAIL" "$E2E_OUT/email-worker.log"; then
    echo "email: delivered to the Email Worker binding" | tee "$E2E_OUT/email_check.txt"
  else
    echo "email: no send_email call in the Worker log" | tee "$E2E_OUT/email_check.txt"; EMAIL_RC=1
  fi
  dc logs --no-color api 2>/dev/null | grep -iE 'email|mail' | tail -20 >> "$E2E_OUT/email_check.txt" || true
fi

echo "== LeLab load check"
LELAB_RC=0
if [[ -x "$E2E_LELAB_PY" ]] && compgen -G "$E2E_OUT/pulled/*/pretrained_model" >/dev/null; then
  env -u PYTHONPATH -u AMENT_PREFIX_PATH "$E2E_LELAB_PY" -I "$HERE/lelab_load_check.py" \
    "$E2E_OUT"/pulled/*/ "$E2E_OUT"/ui-bundle/*/ 2>&1 | tee "$E2E_OUT/lelab_load_check.txt" || LELAB_RC=${PIPESTATUS[0]}
else
  echo "skipped: no LeLab venv at $E2E_LELAB_PY or no pulled bundle" | tee "$E2E_OUT/lelab_load_check.txt"
  LELAB_RC=1
fi

echo "== ONNX (bundle's onnx/infer_onnx.py with onnxruntime, throwaway uv env)"
ONNX_RC=0
for b in "$E2E_OUT"/ui-bundle/*/; do
  if [[ -f "$b/onnx/infer_onnx.py" ]]; then
    env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run --no-project --isolated --python 3.12 --with-requirements "$b/onnx/requirements.txt" \
      python -I "$b/onnx/infer_onnx.py" --bundle "$b" --selftest --steps 5 2>&1 | tee -a "$E2E_OUT/onnx_check.txt" \
      || ONNX_RC=${PIPESTATUS[0]}
  else
    echo "no onnx/infer_onnx.py in $b" | tee -a "$E2E_OUT/onnx_check.txt"; ONNX_RC=1
  fi
done
compgen -G "$E2E_OUT/ui-bundle/*/" >/dev/null || { echo "no UI bundle" | tee -a "$E2E_OUT/onnx_check.txt"; ONNX_RC=1; }

echo "pytest rc=$PYTEST_RC lelab rc=$LELAB_RC onnx rc=$ONNX_RC email rc=$EMAIL_RC"
exit $(( PYTEST_RC != 0 || LELAB_RC != 0 || ONNX_RC != 0 || EMAIL_RC != 0 ))
