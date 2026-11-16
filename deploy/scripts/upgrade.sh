#!/usr/bin/env bash
# Upgrade the production stack to images already built with build-images.sh --tag NEW.
#
#   deploy/scripts/upgrade.sh NEW_TAG [--version X.Y.Z] [--wait-until HH:MM]
#
# Steps: refuse if a NEW_TAG image is missing -> wait while training runs are active (until
# --wait-until, then give up without touching anything) -> fresh backup -> switch
# HIBISCUS_IMAGE_TAG (and HIBISCUS_VERSION) in deploy/.env -> compose up --wait -> smoke checks.
# If anything after the switch fails, it restores the previous .env and brings the old images
# back, unless the database schema (alembic head) changed: then it stops and says so, because
# old code on a new schema needs the restore steps in docs/runbook/upgrade.md.
# Every step goes to deploy/upgrade-logs/<timestamp>.log; the last line is RESULT: ...
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY="$ROOT/deploy"
ENV_FILE="$DEPLOY/.env"
COMPOSE=(docker compose -p hibiscus --project-directory "$DEPLOY" -f "$DEPLOY/docker-compose.yml")
IMAGES=(api web worker-gpu worker-gpu-pascal worker-cpu)
ACTIVE="'queued','preparing','running','pausing','exporting','cancelling'"

NEW="${1:?usage: upgrade.sh NEW_TAG [--version X.Y.Z] [--wait-until HH:MM]}"; shift
VERSION=""; WAIT_UNTIL="02:00"
while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --wait-until) WAIT_UNTIL="$2"; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done

mkdir -p "$DEPLOY/upgrade-logs"
LOG="$DEPLOY/upgrade-logs/$(date +%Y%m%d-%H%M%S)-$NEW.log"
exec > >(tee -a "$LOG") 2>&1
say() { echo "[$(date '+%F %T')] $*"; }
finish() { say "RESULT: $1"; exit "${2:-0}"; }

psql_q() {
  # shellcheck disable=SC2016  # $POSTGRES_USER and $0 expand inside the container shell
  "${COMPOSE[@]}" exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d hibiscus -Atc "$0"' "$1"
}
env_get() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2-; }
env_set() {
  if grep -qE "^$1=" "$ENV_FILE"; then sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"; else echo "$1=$2" >> "$ENV_FILE"; fi
}

smoke() {
  local base="http://127.0.0.1:18000" code
  code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$base/healthz") || code=000
  [ "$code" = 200 ] || { say "smoke: /healthz -> $code"; return 1; }
  code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$base/login") || code=000
  [ "$code" = 200 ] || { say "smoke: /login -> $code"; return 1; }
  code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$base/api/v1/auth/me") || code=000
  [ "$code" = 401 ] || { say "smoke: /api/v1/auth/me -> $code (want 401)"; return 1; }
  # both GPU workers must heartbeat with the new images
  local fresh i
  for i in $(seq 1 18); do
    fresh=$(psql_q "select count(*) from gpu_nodes where status='online' and last_heartbeat_at > now() - interval '60 seconds'" || echo 0)
    [ "${fresh:-0}" -ge 2 ] && { say "smoke: ok (2 GPU workers online)"; return 0; }
    sleep 10
  done
  say "smoke: only ${fresh:-0} GPU worker(s) heartbeating"; return 1
}

say "upgrade to $NEW requested (log $LOG)"
for i in "${IMAGES[@]}"; do
  docker image inspect "hibiscus/$i:$NEW" >/dev/null 2>&1 || finish "ABORTED, image hibiscus/$i:$NEW not built; nothing changed" 1
done
OLD_TAG="$(env_get HIBISCUS_IMAGE_TAG)"; OLD_VERSION="$(env_get HIBISCUS_VERSION)"
[ "$OLD_TAG" != "$NEW" ] || finish "NOTHING TO DO, already on $NEW"

# Wait for active training runs to finish; never interrupt one.
while :; do
  active=$(psql_q "select count(*) from runs where status in ($ACTIVE)")
  [ "$active" = 0 ] && break
  # --wait-until is a time after midnight (e.g. 02:00); give up between it and noon.
  now=$((10#$(date +%H%M))); limit=$((10#${WAIT_UNTIL/:/}))
  if [ -n "$WAIT_UNTIL" ] && [ "$now" -ge "$limit" ] && [ "$now" -lt 1200 ]; then
    finish "POSTPONED, $active run(s) still active at $(date +%H:%M); nothing changed" 3
  fi
  say "$active run(s) active, waiting 5 min"
  sleep 300
done

say "compose policy check"
make -C "$ROOT" --no-print-directory config >/dev/null || finish "ABORTED, compose policy check failed; nothing changed" 1

say "backup before upgrade"
"${COMPOSE[@]}" exec -T backup bash /backup/pg-backup.sh
HEAD_BEFORE="$(psql_q 'select version_num from alembic_version' || true)"
cp -p "$ENV_FILE" "$ENV_FILE.before-$NEW"

say "switching $OLD_TAG -> $NEW"
env_set HIBISCUS_IMAGE_TAG "$NEW"
[ -n "$VERSION" ] && env_set HIBISCUS_VERSION "$VERSION"

if "${COMPOSE[@]}" up -d --wait --wait-timeout 300 && smoke; then
  say "now running $NEW ($(psql_q 'select version_num from alembic_version'))"
  finish "OK, upgraded $OLD_TAG -> $NEW"
fi

say "upgrade failed, rolling back"
HEAD_AFTER="$(psql_q 'select version_num from alembic_version' || true)"
if [ "$HEAD_BEFORE" != "$HEAD_AFTER" ]; then
  finish "FAILED, schema moved $HEAD_BEFORE -> $HEAD_AFTER; NOT rolled back automatically, follow docs/runbook/upgrade.md (env backup: $ENV_FILE.before-$NEW)" 1
fi
cp -p "$ENV_FILE.before-$NEW" "$ENV_FILE"
if "${COMPOSE[@]}" up -d --wait --wait-timeout 300 && smoke; then
  finish "ROLLED BACK to $OLD_TAG (version $OLD_VERSION); the new images need a look" 1
fi
finish "FAILED, rollback to $OLD_TAG did not pass the smoke checks either; needs a human" 1
