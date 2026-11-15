#!/usr/bin/env bash
# Healthcheck for the `backup` service: healthy when the last successful dump is younger than
# BACKUP_MAX_AGE_SECONDS (default 26 h), or when the scheduler started less than that long ago
# and simply has not reached its first run yet.
set -euo pipefail

MAX_AGE="${BACKUP_MAX_AGE_SECONDS:-93600}"
now=$(date +%s)
last_file="${BACKUP_DIR:-/backups}/last-success"

if [[ -f "$last_file" ]]; then
  last=$(cat "$last_file")
  if (( now - last <= MAX_AGE )); then exit 0; fi
fi
if [[ -f /tmp/backup-loop.started ]]; then
  started=$(cat /tmp/backup-loop.started)
  if (( now - started <= MAX_AGE )) && [[ ! -f "$last_file" || $(cat "$last_file") -lt $started ]]; then
    exit 0
  fi
fi
echo "no successful backup within ${MAX_AGE}s" >&2
exit 1
