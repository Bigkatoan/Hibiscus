#!/usr/bin/env bash
# Nightly scheduler for pg-backup.sh (PID 1 of the `backup` service). No cron daemon needed:
# sleeps until the next BACKUP_AT (HH:MM, container TZ), runs one backup, repeats. A failed
# backup is retried after BACKUP_RETRY_SECONDS (default 1 h); the healthcheck
# (backup-health.sh) turns the container unhealthy when no backup succeeded for 26 h.
#   BACKUP_RUN_ON_START=1   also take a backup immediately at start-up
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AT="${BACKUP_AT:-03:15}"
RETRY="${BACKUP_RETRY_SECONDS:-3600}"
date +%s > /tmp/backup-loop.started

if ! [[ "$AT" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
  echo "backup-loop: BACKUP_AT must be HH:MM, got '$AT'" >&2
  exit 2
fi

seconds_until() {
  local now target
  now=$(date +%s)
  target=$(date -d "today ${AT}" +%s)
  if (( target <= now )); then target=$(date -d "tomorrow ${AT}" +%s); fi
  echo $(( target - now ))
}

trap 'exit 0' TERM INT

if [[ "${BACKUP_RUN_ON_START:-0}" == "1" ]]; then
  bash "$HERE/pg-backup.sh" || echo "backup-loop: start-up backup failed" >&2
fi

while true; do
  wait_s=$(seconds_until)
  echo "backup-loop: next backup at ${AT} (in ${wait_s}s)"
  sleep "$wait_s" &
  wait $!
  until bash "$HERE/pg-backup.sh"; do
    echo "backup-loop: backup failed, retrying in ${RETRY}s" >&2
    sleep "$RETRY" &
    wait $!
  done
done
