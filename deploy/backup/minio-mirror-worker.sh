#!/usr/bin/env bash
# Inside the runner container started by minio-mirror.sh: encrypt every object of the given
# buckets from MinIO (alias `lt`, MC_HOST_lt) into /mirror/<bucket>/<key>.gpg.
#   minio-mirror-worker.sh BUCKET...        (MIRROR_REMOVE=--remove prunes vanished objects)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=SCRIPTDIR/crypt.sh
source "$HERE/crypt.sh"
backup_require_passphrase
backup_crypt_init
work="$(mktemp -d)"
trap 'rm -rf "$work"; backup_crypt_cleanup' EXIT

# Keyed hash of the ETag (an ETag is usually the MD5 of the plaintext; do not store it in clear).
etag_tag() { printf '%s:%s' "$HIBISCUS_BACKUP_PASSPHRASE" "$1" | sha256sum | cut -d' ' -f1; }

total_new=0
for bucket in "$@"; do
  root="/mirror/$bucket"
  mkdir -p "$root"
  listing="$work/$bucket.jsonl"
  seen="$work/$bucket.seen"
  : > "$seen"
  mc ls --recursive --json "lt/$bucket" > "$listing"
  new=0
  kept=0
  while IFS= read -r line; do
    [[ "$line" == *'"type":"file"'* ]] || continue
    if ! [[ "$line" =~ \"key\":\"([^\"\\]+)\" ]]; then
      echo "skip: object key with escaped characters in $bucket: ${line:0:200}" >&2
      continue
    fi
    key="${BASH_REMATCH[1]}"
    case "/$key/" in
      */../*|*/./*|//*) echo "skip: unsafe object key '$key' in $bucket" >&2; continue ;;
    esac
    etag=""
    if [[ "$line" =~ \"etag\":\"([^\"]*)\" ]]; then etag="${BASH_REMATCH[1]}"; fi
    out="$root/$key.gpg"
    printf '%s\n' "$key.gpg" >> "$seen"
    tag="$(etag_tag "$etag")"
    if [[ -n "$etag" && -f "$out" && -f "$out.etag" && "$(cat "$out.etag")" == "$tag" ]]; then
      kept=$((kept + 1))
      continue
    fi
    mkdir -p "$(dirname "$out")"
    mc cat "lt/$bucket/$key" | backup_encrypt_stream "$out.partial"
    mv "$out.partial" "$out"
    printf '%s' "$tag" > "$out.etag"
    new=$((new + 1))
  done < "$listing"
  removed=0
  if [[ "${MIRROR_REMOVE:-}" == "--remove" ]]; then
    sort -o "$seen" "$seen"
    while IFS= read -r rel; do
      rm -f "$root/$rel" "$root/$rel.etag"
      removed=$((removed + 1))
    done < <(cd "$root" && find . -type f -name '*.gpg' -printf '%P\n' | sort | comm -23 - "$seen")
  fi
  echo "$bucket: ${new} encrypted, ${kept} unchanged, ${removed} removed"
  total_new=$((total_new + new))
done
echo "mirror done: ${total_new} objects (re)encrypted"
