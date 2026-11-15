#!/usr/bin/env bash
# Symmetric encryption helpers for backups (SEC-infra-2). Sourced by pg-backup.sh, restore.sh,
# minio-mirror-worker.sh and decrypt-tree.sh; not executed directly.
#
# Format: OpenPGP symmetric (gpg --symmetric), AES-256, SHA-512 S2K with the maximum iteration
# count, MDC integrity protection (gpg refuses to decrypt a modified file). The key is the
# passphrase in HIBISCUS_BACKUP_PASSPHRASE (deploy/.env); it is passed to gpg on a pipe, never on
# the command line or in a file. Any standard gpg can decrypt the output:
#   gpg --decrypt --pinentry-mode loopback hibiscus-....dump.gpg > plain.dump
#
#   backup_crypt_init               create a private GNUPGHOME (call once; removed on EXIT by caller)
#   backup_encrypt IN OUT           encrypt file IN to OUT
#   backup_encrypt_stream OUT       encrypt stdin to OUT
#   backup_decrypt IN OUT|-         decrypt IN to OUT (or stdout)

BACKUP_GPG="${HIBISCUS_GPG:-gpg}"

backup_require_passphrase() {
  if [[ -z "${HIBISCUS_BACKUP_PASSPHRASE:-}" || "${HIBISCUS_BACKUP_PASSPHRASE}" == "CHANGE_ME" ]]; then
    echo "HIBISCUS_BACKUP_PASSPHRASE is not set: refusing to write or read an unencrypted backup" >&2
    return 1
  fi
  if (( ${#HIBISCUS_BACKUP_PASSPHRASE} < 16 )); then
    echo "HIBISCUS_BACKUP_PASSPHRASE must be at least 16 characters" >&2
    return 1
  fi
}

backup_crypt_init() {
  command -v "$BACKUP_GPG" >/dev/null || { echo "gpg not found (install gnupg)" >&2; return 1; }
  BACKUP_GNUPGHOME="$(mktemp -d "${TMPDIR:-/tmp}/hibiscus-gpg.XXXXXX")"
  chmod 700 "$BACKUP_GNUPGHOME"
  export BACKUP_GNUPGHOME
}

backup_crypt_cleanup() {
  if [[ -n "${BACKUP_GNUPGHOME:-}" && -d "$BACKUP_GNUPGHOME" ]]; then
    gpgconf --homedir "$BACKUP_GNUPGHOME" --kill gpg-agent >/dev/null 2>&1 || true
    rm -rf "$BACKUP_GNUPGHOME"
  fi
}

_backup_gpg() {
  "$BACKUP_GPG" --homedir "$BACKUP_GNUPGHOME" --batch --yes --quiet --no-tty --no-symkey-cache \
    --pinentry-mode loopback --passphrase-fd 3 "$@" 3< <(printf '%s' "$HIBISCUS_BACKUP_PASSPHRASE")
}

backup_encrypt() {
  _backup_gpg --symmetric --cipher-algo AES256 --s2k-mode 3 --s2k-digest-algo SHA512 \
    --s2k-count 65011712 --compress-algo none --force-mdc --output "$2" "$1"
}

backup_encrypt_stream() {
  _backup_gpg --symmetric --cipher-algo AES256 --s2k-mode 3 --s2k-digest-algo SHA512 \
    --s2k-count 65011712 --compress-algo none --force-mdc --output "$1"
}

backup_decrypt() {
  _backup_gpg --decrypt --output "$2" "$1"
}
