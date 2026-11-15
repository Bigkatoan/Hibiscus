#!/usr/bin/env bash
# First-start initialisation of the Hibiscus database (run by the postgres image entrypoint only
# when the data directory is empty). Creates:
#   * role  $HIBISCUS_DB_USER   — the application role; owns database $HIBISCUS_DB_NAME and every
#                                table (Alembic migrations run as this role). Not a superuser.
#   * role  hibiscus_monitor    — Prometheus postgres-exporter. pg_monitor + EXECUTE on the
#                                SECURITY DEFINER functions in schema `monitoring`; it cannot read
#                                any application table directly (users, tokens, ...).
#   * schema monitoring        — aggregate-only functions used by
#                                deploy/observability/postgres-exporter/queries.yaml.
# The functions are PL/pgSQL, so they compile before the migrations create the tables they read.
# Status values are VARCHAR + CHECK in the contract schema (models.py `_enum`, native_enum=False),
# so the zero-filled status lists below mirror RunStatus / JobKind / JobStatus / JobResource.
# Re-running is safe and is how upgrades apply new monitoring functions:
#   docker compose exec postgres bash /docker-entrypoint-initdb.d/10-hibiscus.sh
set -euo pipefail

: "${HIBISCUS_DB_NAME:?}" "${HIBISCUS_DB_USER:?}" "${HIBISCUS_DB_PASSWORD:?}" "${HIBISCUS_DB_MONITOR_PASSWORD:?}"

psql_su() { psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" "$@"; }

psql_su --dbname postgres \
  -v app_user="$HIBISCUS_DB_USER" -v app_pass="$HIBISCUS_DB_PASSWORD" \
  -v app_db="$HIBISCUS_DB_NAME" -v mon_pass="$HIBISCUS_DB_MONITOR_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'app_user')
 WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_user') \gexec
ALTER ROLE :"app_user" WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_pass';
SELECT 'CREATE ROLE hibiscus_monitor LOGIN'
 WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hibiscus_monitor') \gexec
ALTER ROLE hibiscus_monitor WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'mon_pass'
  CONNECTION LIMIT 5;
GRANT pg_monitor TO hibiscus_monitor;
SELECT format('CREATE DATABASE %I OWNER %I ENCODING ''UTF8'' TEMPLATE template0', :'app_db', :'app_user')
 WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'app_db') \gexec
REVOKE ALL ON DATABASE :"app_db" FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE :"app_db" TO :"app_user";
GRANT CONNECT ON DATABASE :"app_db" TO hibiscus_monitor;
SQL

psql_su --dbname "$HIBISCUS_DB_NAME" -v app_user="$HIBISCUS_DB_USER" <<'SQL'
ALTER SCHEMA public OWNER TO :"app_user";
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA IF NOT EXISTS monitoring AUTHORIZATION :"app_user";
REVOKE ALL ON SCHEMA monitoring FROM PUBLIC;
GRANT USAGE ON SCHEMA monitoring TO hibiscus_monitor;
SQL

# Functions are created by the application role so SECURITY DEFINER runs with its (non-superuser)
# rights. search_path is pinned to defeat search-path hijacking.
psql_su --dbname "$HIBISCUS_DB_NAME" -v app_user="$HIBISCUS_DB_USER" <<'SQL'
SET ROLE :"app_user";

CREATE OR REPLACE FUNCTION monitoring.run_status_counts()
RETURNS TABLE (status text, runs bigint)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  RETURN QUERY
    SELECT v.s::text, count(r.id)
      FROM (VALUES ('queued'),('preparing'),('running'),('pausing'),('paused'),('exporting'),('succeeded'),('failed'),('cancelling'),('cancelled')) AS v(s)
      LEFT JOIN runs r ON r.status = v.s
     GROUP BY v.s ORDER BY v.s;
END $$;

CREATE OR REPLACE FUNCTION monitoring.run_queue()
RETURNS TABLE (queued bigint, oldest_queued_seconds double precision, active bigint)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  RETURN QUERY
    SELECT count(*) FILTER (WHERE r.status = 'queued'),
           COALESCE(EXTRACT(EPOCH FROM now() - min(r.status_changed_at) FILTER (WHERE r.status = 'queued')), 0)::double precision,
           count(*) FILTER (WHERE r.status IN ('preparing','running','pausing','exporting','cancelling'))
      FROM runs r;
END $$;

CREATE OR REPLACE FUNCTION monitoring.job_status_counts()
RETURNS TABLE (kind text, resource text, status text, jobs bigint)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  RETURN QUERY
    SELECT vk.k::text, j.resource::text, vs.s::text, count(j.id)
      FROM (VALUES ('validate_dataset'),('import_hf_dataset'),('merge_datasets'),('export_model'),('eval_checkpoint'),('push_model_hub'),('estimate_resources')) AS vk(k)
     CROSS JOIN (VALUES ('queued'),('running'),('succeeded'),('failed'),('cancelled')) AS vs(s)
      LEFT JOIN jobs j ON j.kind = vk.k AND j.status = vs.s
     GROUP BY vk.k, j.resource, vs.s
    HAVING count(j.id) > 0 OR vs.s = 'queued';
END $$;

CREATE OR REPLACE FUNCTION monitoring.job_queue()
RETURNS TABLE (resource text, queued bigint, oldest_queued_seconds double precision)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  RETURN QUERY
    SELECT vr.res::text, count(j.id),
           COALESCE(EXTRACT(EPOCH FROM now() - min(j.created_at)), 0)::double precision
      FROM (VALUES ('cpu'),('gpu')) AS vr(res)
      LEFT JOIN jobs j ON j.resource = vr.res AND j.status = 'queued'
     GROUP BY vr.res;
END $$;

CREATE OR REPLACE FUNCTION monitoring.gpu_nodes()
RETURNS TABLE (node text, name text, status text, online double precision,
               heartbeat_age_seconds double precision, busy double precision)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  RETURN QUERY
    SELECT g.id::text, g.name::text, g.status::text,
           CASE WHEN g.status = 'online' THEN 1 ELSE 0 END::double precision,
           COALESCE(EXTRACT(EPOCH FROM now() - g.last_heartbeat_at), -1)::double precision,
           CASE WHEN g.current_run_id IS NULL THEN 0 ELSE 1 END::double precision
      FROM gpu_nodes g;
END $$;

CREATE OR REPLACE FUNCTION monitoring.upload_sessions()
RETURNS TABLE (status text, sessions bigint)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  RETURN QUERY
    SELECT u.status::text, count(*)
      FROM upload_sessions u
     GROUP BY u.status;
END $$;

RESET ROLE;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA monitoring FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA monitoring TO hibiscus_monitor;
SQL

echo "hibiscus: database ${HIBISCUS_DB_NAME}, roles ${HIBISCUS_DB_USER} + hibiscus_monitor ready"
