#!/usr/bin/env bash
# Decrypt an encrypted MinIO mirror (minio-mirror.sh) back into plain files for a restore:
#
#   HIBISCUS_BACKUP_PASSPHRASE=... deploy/backup/decrypt-tree.sh /mnt/backup/hibiscus-minio /restore/minio
#
# <SRC>/<bucket>/<key>.gpg -> <DEST>/<bucket>/<key>. The passphrase is read from the environment
# or from $HIBISCUS_ENV_FILE (default deploy/.env). Then push the plain tree back into MinIO, e.g.
#   mc mirror --overwrite /restore/minio/hibiscus-datasets lt/hibiscus-datasets
# (docs/runbook/backup-restore.md). DEST holds plaintext: put it on the server's own disk and
# delete it after the restore.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:?usage: $0 SRC_DIR DEST_DIR}"
DEST="${2:?usage: $0 SRC_DIR DEST_DIR}"
SRC="${SRC%/}"
ENV_FILE="${HIBISCUS_ENV_FILE:-$DEPLOY_DIR/.env}"
if [[ -z "${HIBISCUS_BACKUP_PASSPHRASE:-}" && -f "$ENV_FILE" ]]; then
  HIBISCUS_BACKUP_PASSPHRASE="$(grep -E '^HIBISCUS_BACKUP_PASSPHRASE=' "$ENV_FILE" | tail -1 | cut -d= -f2-)"
  HIBISCUS_BACKUP_PASSPHRASE="${HIBISCUS_BACKUP_PASSPHRASE%\"}"
  HIBISCUS_BACKUP_PASSPHRASE="${HIBISCUS_BACKUP_PASSPHRASE#\"}"
fi
export HIBISCUS_BACKUP_PASSPHRASE
# shellcheck source=SCRIPTDIR/crypt.sh
source "$DEPLOY_DIR/backup/crypt.sh"
backup_require_passphrase
backup_crypt_init
trap backup_crypt_cleanup EXIT

n=0
while IFS= read -r -d '' f; do
  rel="${f#"$SRC"/}"
  out="$DEST/${rel%.gpg}"
  mkdir -p "$(dirname "$out")"
  backup_decrypt "$f" "$out"
  n=$((n + 1))
done < <(find "$SRC" -type f -name '*.gpg' -print0)
echo "decrypted ${n} files -> $DEST"
