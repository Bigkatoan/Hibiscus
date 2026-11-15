#!/usr/bin/env bash
# Print freshly generated values for every secret in deploy/.env.example.
#   deploy/scripts/gen-secrets.sh > /tmp/new-secrets && review && merge into deploy/.env
# Output goes to stdout only; nothing is written to disk by this script.
set -euo pipefail

rand_hex() { openssl rand -hex "$1"; }
rand_b64() { openssl rand -base64 "$1" | tr -d '\n'; }
# Ed25519 PKCS8 PEM on one line with literal \n separators, for a DOUBLE-quoted .env value
# (compose's env-file parser turns \n back into newlines).
ed25519_pem() { openssl genpkey -algorithm ed25519 | awk '{printf "%s\\n", $0}'; }

cat <<EOF
POSTGRES_SUPERUSER_PASSWORD=$(rand_hex 24)
HIBISCUS_DB_PASSWORD=$(rand_hex 24)
HIBISCUS_DB_MONITOR_PASSWORD=$(rand_hex 24)
HIBISCUS_REDIS_PASSWORD=$(rand_hex 24)
MINIO_ROOT_PASSWORD=$(rand_hex 24)
HIBISCUS_S3_SECRET_KEY=$(rand_hex 24)
HIBISCUS_DATA_KEY=$(rand_b64 32)
HIBISCUS_JWT_PRIVATE_KEY="$(ed25519_pem)"
HIBISCUS_CURSOR_SECRET=$(rand_hex 32)
HIBISCUS_EMAIL_WORKER_SECRET=$(rand_hex 32)
HIBISCUS_BACKUP_PASSPHRASE=$(rand_hex 32)
GRAFANA_ADMIN_PASSWORD=$(rand_hex 16)
EOF
