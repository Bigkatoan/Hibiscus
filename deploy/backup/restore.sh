#!/usr/bin/env bash
# Restore a Hibiscus Postgres dump produced by pg-backup.sh. Run on the host from anywhere.
#
#   deploy/backup/restore.sh BACKUP.dump.gpg [--target-db NAME] [--yes] [--no-stop]
#
#   --target-db NAME  restore into NAME instead of the live database (restore drill; the live DB
#                     and the running services are not touched). Default: $HIBISCUS_DB_NAME.
#   --yes             do not ask for confirmation (required in scripts)
#   --no-stop         do not stop/start api + workers around an in-place restore
#
# Environment:
#   HIBISCUS_PG_EXEC   command prefix that runs a program inside the Postgres container with stdin
#                     attached (default: "docker compose --project-directory <deploy> exec -T postgres")
#   HIBISCUS_COMPOSE   compose command used for stop/start (default: "docker compose --project-directory <deploy>")
#   HIBISCUS_DB_NAME / HIBISCUS_DB_USER   default hibiscus / hibiscus
#   HIBISCUS_BACKUP_PASSPHRASE  decrypts *.dump.gpg (SEC-infra-2); when unset it is read from
#                     $HIBISCUS_ENV_FILE (default deploy/.env). Needs gpg on the host.
#
# Procedure: verify sha256 -> decrypt into a private temp file (*.gpg) -> (stop api + workers)
# -> drop + recreate target DB owned by the app role -> pg_restore --exit-on-error as the app
# role -> sanity check -> (start services). Unencrypted *.dump files of older releases are still
# accepted (with a warning).
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DUMP=""
TARGET=""
ASSUME_YES=0
STOP=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-db) TARGET="${2:?}"; shift 2 ;;
    --yes) ASSUME_YES=1; shift ;;
    --no-stop) STOP=0; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    -*) echo "unknown option $1" >&2; exit 2 ;;
    *) DUMP="$1"; shift ;;
  esac
done
[[ -n "$DUMP" && -f "$DUMP" ]] || { echo "usage: $0 BACKUP.dump.gpg [--target-db NAME] [--yes]" >&2; exit 2; }

DB_NAME="${HIBISCUS_DB_NAME:-hibiscus}"
DB_USER="${HIBISCUS_DB_USER:-hibiscus}"
TARGET="${TARGET:-$DB_NAME}"
read -r -a PG_EXEC <<< "${HIBISCUS_PG_EXEC:-docker compose --project-directory $DEPLOY_DIR exec -T postgres}"
read -r -a COMPOSE <<< "${HIBISCUS_COMPOSE:-docker compose --project-directory $DEPLOY_DIR}"
APP_SERVICES=(proxy api worker-cuda0 worker-cuda1 worker-cpu backup)

if [[ ! "$TARGET" =~ ^[a-z_][a-z0-9_]{0,62}$ ]]; then
  echo "invalid database name: $TARGET" >&2; exit 2
fi

if [[ -f "$DUMP.sha256" ]]; then
  (cd "$(dirname "$DUMP")" && sha256sum --check --status "$(basename "$DUMP").sha256") \
    || { echo "sha256 mismatch for $DUMP" >&2; exit 1; }
  echo "checksum ok"
else
  echo "warning: no $DUMP.sha256 next to the dump; integrity not verified" >&2
fi

INPUT="$DUMP"
if [[ "$DUMP" == *.gpg ]]; then
  # shellcheck source=SCRIPTDIR/crypt.sh
  source "$DEPLOY_DIR/backup/crypt.sh"
  if [[ -z "${HIBISCUS_BACKUP_PASSPHRASE:-}" ]]; then
    ENV_FILE="${HIBISCUS_ENV_FILE:-$DEPLOY_DIR/.env}"
    if [[ -f "$ENV_FILE" ]]; then
      HIBISCUS_BACKUP_PASSPHRASE="$(grep -E '^HIBISCUS_BACKUP_PASSPHRASE=' "$ENV_FILE" | tail -1 | cut -d= -f2-)"
      HIBISCUS_BACKUP_PASSPHRASE="${HIBISCUS_BACKUP_PASSPHRASE%\"}"
      HIBISCUS_BACKUP_PASSPHRASE="${HIBISCUS_BACKUP_PASSPHRASE#\"}"
      export HIBISCUS_BACKUP_PASSPHRASE
    fi
  fi
  backup_require_passphrase || exit 1
  backup_crypt_init
  PLAIN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hibiscus-restore.XXXXXX")"   # 0700
  trap 'rm -rf "$PLAIN_DIR"; backup_crypt_cleanup' EXIT
  INPUT="$PLAIN_DIR/restore.dump"
  if ! backup_decrypt "$DUMP" "$INPUT"; then
    echo "cannot decrypt $DUMP (wrong HIBISCUS_BACKUP_PASSPHRASE or corrupted file)" >&2
    exit 1
  fi
  echo "decrypted ok"
else
  echo "warning: $(basename "$DUMP") is not encrypted (pre-SEC-infra-2 backup)" >&2
fi

in_place=0
[[ "$TARGET" == "$DB_NAME" ]] && in_place=1
if [[ $ASSUME_YES -ne 1 ]]; then
  if [[ $in_place -eq 1 ]]; then
    echo "This REPLACES the live database '$TARGET' with $(basename "$DUMP")."
  else
    echo "This drops and recreates database '$TARGET' from $(basename "$DUMP")."
  fi
  read -r -p "Type the database name to continue: " answer
  [[ "$answer" == "$TARGET" ]] || { echo "aborted"; exit 1; }
fi

if [[ $in_place -eq 1 && $STOP -eq 1 ]]; then
  echo "stopping application services: ${APP_SERVICES[*]}"
  "${COMPOSE[@]}" stop "${APP_SERVICES[@]}" || true
fi

psql_su() { "${PG_EXEC[@]}" psql -v ON_ERROR_STOP=1 -U postgres -d postgres "$@"; }

psql_su -v db="$TARGET" -v owner="$DB_USER" <<'SQL'
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :'db' AND pid <> pg_backend_pid();
SELECT format('DROP DATABASE IF EXISTS %I', :'db') \gexec
SELECT format('CREATE DATABASE %I OWNER %I ENCODING ''UTF8'' TEMPLATE template0', :'db', :'owner') \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'db') \gexec
SELECT format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO %I', :'db', :'owner') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO hibiscus_monitor', :'db') \gexec
SQL
# The dump contains schema public (owned by the app role) and schema monitoring; make the
# empty target match before restoring so ownership and ACLs come out identical.
"${PG_EXEC[@]}" psql -v ON_ERROR_STOP=1 -U postgres -d "$TARGET" -v owner="$DB_USER" \
  -c "ALTER SCHEMA public OWNER TO \"$DB_USER\"" -c "REVOKE ALL ON SCHEMA public FROM PUBLIC" >/dev/null

echo "restoring $(basename "$DUMP") into $TARGET"
"${PG_EXEC[@]}" pg_restore -U postgres --role="$DB_USER" --no-owner --exit-on-error \
  --single-transaction -d "$TARGET" < "$INPUT"

tables=$("${PG_EXEC[@]}" psql -At -U postgres -d "$TARGET" \
  -c "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
echo "restore ok: ${tables} tables in public"

if [[ $in_place -eq 1 && $STOP -eq 1 ]]; then
  echo "starting application services"
  "${COMPOSE[@]}" up -d "${APP_SERVICES[@]}"
fi
