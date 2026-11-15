#!/bin/sh
# Idempotent MinIO bootstrap (runs on every `docker compose up` as the one-shot `minio-init`).
#   * buckets hibiscus-uploads / hibiscus-datasets / hibiscus-artifacts (ADR-0004)
#   * versioning ON for datasets + artifacts (PLAN §6 backups), uploads unversioned
#   * lifecycle: uploads expire after N days and abort incomplete multipart uploads after 2 days;
#     non-current versions in datasets/artifacts expire after N days (bounded disk growth)
#   * a least-privilege application user (API + workers) limited to the three buckets
# The root credentials are used only here and never reach the API or workers.
set -eu

: "${MINIO_ROOT_USER:?}" "${MINIO_ROOT_PASSWORD:?}" "${HIBISCUS_S3_ACCESS_KEY:?}" "${HIBISCUS_S3_SECRET_KEY:?}"
ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"
UPLOADS_DAYS="${HIBISCUS_UPLOADS_EXPIRE_DAYS:-14}"
NONCURRENT_DAYS="${HIBISCUS_NONCURRENT_EXPIRE_DAYS:-30}"
export MC_CONFIG_DIR=/tmp/.mc

i=0
until mc alias set lt "$ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 30 ]; then echo "minio-init: MinIO not reachable at $ENDPOINT" >&2; exit 1; fi
  sleep 2
done

for b in hibiscus-uploads hibiscus-datasets hibiscus-artifacts; do
  mc mb --ignore-existing "lt/$b"
  mc anonymous set none "lt/$b" >/dev/null
done

mc version enable lt/hibiscus-datasets
mc version enable lt/hibiscus-artifacts

# Lifecycle rules are replaced wholesale so re-runs converge on exactly this configuration.
cat > /tmp/uploads-lifecycle.json <<EOF
{"Rules": [
  {"ID": "expire-uploads", "Status": "Enabled", "Filter": {"Prefix": ""},
   "Expiration": {"Days": ${UPLOADS_DAYS}},
   "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 2}}
]}
EOF
mc ilm import lt/hibiscus-uploads < /tmp/uploads-lifecycle.json >/dev/null

cat > /tmp/versioned-lifecycle.json <<EOF
{"Rules": [
  {"ID": "expire-noncurrent", "Status": "Enabled", "Filter": {"Prefix": ""},
   "NoncurrentVersionExpiration": {"NoncurrentDays": ${NONCURRENT_DAYS}},
   "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 2}}
]}
EOF
mc ilm import lt/hibiscus-datasets < /tmp/versioned-lifecycle.json >/dev/null
mc ilm import lt/hibiscus-artifacts < /tmp/versioned-lifecycle.json >/dev/null

mc admin policy create lt hibiscus-app /init/hibiscus-app-policy.json >/dev/null
# `user add` is an upsert: re-running with a new secret rotates it (docs/runbook/secrets.md).
mc admin user add lt "$HIBISCUS_S3_ACCESS_KEY" "$HIBISCUS_S3_SECRET_KEY" >/dev/null
# `attach` fails when the policy is already attached; that is the converged state.
mc admin policy attach lt hibiscus-app --user "$HIBISCUS_S3_ACCESS_KEY" >/dev/null 2>&1 || true
mc admin user enable lt "$HIBISCUS_S3_ACCESS_KEY" >/dev/null

echo "minio-init: buckets, versioning, lifecycle and user '$HIBISCUS_S3_ACCESS_KEY' ready"
mc version info lt/hibiscus-datasets
mc version info lt/hibiscus-artifacts
