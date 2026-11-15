#!/usr/bin/env bash
# One Postgres backup: custom-format pg_dump -> verify -> encrypt -> verify round trip -> sha256
# -> atomically publish -> prune. Runs inside the `backup` service (postgres image, which ships
# gpg) but works anywhere with pg_dump >= 16, gpg and libpq env vars (PGHOST, PGPORT, PGDATABASE,
# PGUSER, PGPASSWORD).
#
#   BACKUP_DIR                  target directory (default /backups)
#   BACKUP_RETENTION_DAYS       delete dumps older than this many days (default 14; 0 = keep all)
#   HIBISCUS_BACKUP_PASSPHRASE  (required) encryption passphrase, see crypt.sh (SEC-infra-2)
#
# Output files:  hibiscus-<db>-<UTC timestamp>.dump.gpg  + .dump.gpg.sha256  ;  last-success (epoch)
# The plaintext dump only ever exists in a private temp directory inside the container, never in
# BACKUP_DIR (a host directory / NAS). Restore: deploy/backup/restore.sh (decrypts transparently).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=SCRIPTDIR/crypt.sh
source "$HERE/crypt.sh"

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
DB="${PGDATABASE:?PGDATABASE is required}"

log() { printf '{"ts":"%s","service":"backup","level":"%s","msg":"%s"}\n' "$(date -u +%FT%TZ)" "$1" "$2"; }

if ! backup_require_passphrase; then
  log error "HIBISCUS_BACKUP_PASSPHRASE missing: no unencrypted backup is written"
  exit 1
fi

mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
final="$BACKUP_DIR/hibiscus-${DB}-${stamp}.dump.gpg"
partial="$final.partial"
# mktemp -d is 0700: the plaintext dump inside is private to this process user.
work="$(mktemp -d "${TMPDIR:-/tmp}/hibiscus-backup.XXXXXX")"
cleanup() { rm -f "$partial"; rm -rf "$work"; backup_crypt_cleanup; }
trap cleanup EXIT
backup_crypt_init
plain="$work/plain.dump"

started=$(date +%s)
log info "pg_dump ${DB} -> ${final}"
pg_dump --format=custom --compress=6 --no-password --file="$plain" "$DB"

# A dump that pg_restore cannot list is not a backup.
entries=$(pg_restore --list "$plain" | grep -c -v '^;' || true)
if [[ "$entries" -lt 1 ]]; then
  log error "dump verification failed (no TOC entries)"
  exit 1
fi

backup_encrypt "$plain" "$partial"
# Prove the published file decrypts back to exactly what pg_restore just verified.
want=$(sha256sum < "$plain" | cut -d' ' -f1)
got=$(backup_decrypt "$partial" - | sha256sum | cut -d' ' -f1)
if [[ "$want" != "$got" ]]; then
  log error "encrypted dump does not decrypt to the verified dump"
  exit 1
fi
rm -f "$plain"

mv "$partial" "$final"
(cd "$BACKUP_DIR" && sha256sum "$(basename "$final")" > "$(basename "$final").sha256")
date +%s > "$BACKUP_DIR/last-success"
size=$(stat -c %s "$final")
log info "backup ok: $(basename "$final") bytes=${size} toc_entries=${entries} encrypted=aes256 seconds=$(( $(date +%s) - started ))"

if [[ "$RETENTION_DAYS" -gt 0 ]]; then
  # *.dump: unencrypted dumps of releases before SEC-infra-2 age out the same way.
  while IFS= read -r old; do
    rm -f "$old" "$old.sha256"
    log info "pruned $(basename "$old")"
  done < <(find "$BACKUP_DIR" -maxdepth 1 -type f \
             \( -name "hibiscus-${DB}-*.dump" -o -name "hibiscus-${DB}-*.dump.gpg" \) \
             -mtime "+${RETENTION_DAYS}" | sort)
fi
