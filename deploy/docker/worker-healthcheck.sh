#!/bin/sh
# Docker HEALTHCHECK of the worker images (QC-e2e-08).
#
# * When the worker maintains a heartbeat file ($HIBISCUS_WORKER_HEARTBEAT_FILE, touched by the
#   train / validate main loops), it must have been refreshed within
#   $HIBISCUS_WORKER_HEARTBEAT_MAX_AGE_S seconds (default 120): a wedged main loop -> unhealthy.
# * Until the file exists (older worker builds never write it, and a fresh container has not
#   reached its first loop yet) liveness is "the worker process is running":
#   `python -m $HIBISCUS_WORKER_MODULE` is alive under tini.
#
# The lease heartbeat in Postgres stays the source of truth for job/run ownership (ADR-0002);
# this only lets Docker (and `compose up --wait`) see a dead or wedged process.
set -eu

module="${HIBISCUS_WORKER_MODULE:-train}"
file="${HIBISCUS_WORKER_HEARTBEAT_FILE:-}"
max_age="${HIBISCUS_WORKER_HEARTBEAT_MAX_AGE_S:-120}"

if [ -n "$file" ] && [ -e "$file" ]; then
  now=$(date +%s)
  mtime=$(stat -c %Y "$file")
  age=$((now - mtime))
  if [ "$age" -le "$max_age" ]; then
    exit 0
  fi
  echo "heartbeat file $file is ${age}s old (> ${max_age}s)" >&2
  exit 1
fi

if pgrep -f "^python -m ${module}( |\$)" >/dev/null 2>&1; then
  exit 0
fi
echo "worker process 'python -m ${module}' is not running" >&2
exit 1
