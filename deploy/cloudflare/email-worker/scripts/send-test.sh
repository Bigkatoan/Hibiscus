#!/usr/bin/env bash
# Send one signed test email through the deployed Worker, using the values in deploy/.env.
#   deploy/cloudflare/email-worker/scripts/send-test.sh you@example.com
set -euo pipefail

TO="${1:?usage: $0 recipient@example.com}"
ENV_FILE="${HIBISCUS_ENV_FILE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)/.env}"
get_env() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2-; }
URL="$(get_env HIBISCUS_EMAIL_WORKER_URL)"
SECRET="$(get_env HIBISCUS_EMAIL_WORKER_SECRET)"
[[ -n "$URL" && -n "$SECRET" ]] || { echo "HIBISCUS_EMAIL_WORKER_URL / _SECRET missing in $ENV_FILE" >&2; exit 1; }

TS="$(date +%s)"
BODY=$(printf '{"to":"%s","subject":"Hibiscus email test","text":"If you can read this, the Hibiscus Email Worker works.","message_id":"test-%s"}' "$TO" "$TS")
SIG="v1=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -hex | awk '{print $NF}')"

curl -sS -X POST "$URL" -H "Content-Type: application/json" \
  -H "X-Hibiscus-Timestamp: $TS" -H "X-Hibiscus-Signature: $SIG" --data-binary "$BODY"
echo
