"""Integration: Postgres init script + monitoring functions + postgres-exporter + backup/restore.

Real containers (postgres:16, postgres-exporter) on a throwaway network; the schema is the real
contract schema generated from backend/app/db/models.py (A1). Nothing is published on the host.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_mock_engine
from sqlalchemy.sql.ddl import ExecutableDDLElement

from dockerutil import Docker, docker_available, run, suffix

pytestmark = [pytest.mark.docker, pytest.mark.skipif(not docker_available(), reason="docker unavailable")]

DEPLOY = Path(__file__).resolve().parent.parent
REPO = DEPLOY.parent
PG_IMAGE = os.environ.get(
    "HIBISCUS_POSTGRES_IMAGE",
    "postgres:16.16-trixie@sha256:dd2bf3ce2dc83a81674cf7f217fcfd8a5009a4b325dda5b843bfee82a06cff6f",
)
EXPORTER_IMAGE = os.environ.get(
    "HIBISCUS_PG_EXPORTER_IMAGE",
    "prometheuscommunity/postgres-exporter:v0.20.1@sha256:ac5ec343104fae0e2d84a27bb8d69b38430a11910c5382cad85d478d2bab713e",
)
MINIO_IMAGE = os.environ.get(
    "HIBISCUS_MINIO_IMAGE",
    "pgsty/minio:RELEASE.2026-08-04T00-00-00Z@sha256:b6bfe7239bfc83fb90d31612d9704d86039dd714f7904b3f1ad68f211e602372",
)
MC_IMAGE = os.environ.get(
    "HIBISCUS_MC_IMAGE",
    "pgsty/mc:RELEASE.2026-11-12T00-00-00Z@sha256:b532278b7a3747dbab6fe45eebb40a653efa704e6758e24e9d9ec54fc96c1800",
)
APP_PASSWORD = "app-" + suffix()
MON_PASSWORD = "mon-" + suffix()
PASSPHRASE = "backup-" + suffix() + "-0123456789abcdef"
DUMP_GLOB = "hibiscus-hibiscus-*.dump.gpg"


def contract_ddl() -> str:
    """CREATE statements for every table/enum in backend/app/db/models.py, PostgreSQL dialect."""
    spec = importlib.util.spec_from_file_location(
        "hibiscus_contract_models", REPO / "backend/app/db/models.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    statements: list[str] = []

    def executor(sql: ExecutableDDLElement, *_: object, **__: object) -> None:
        statements.append(str(sql.compile(dialect=engine.dialect)).strip() + ";")

    engine = create_mock_engine("postgresql+psycopg://", executor)
    module.Base.metadata.create_all(engine, checkfirst=False)
    return "\n".join(statements)


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, str]]:
    d = Docker()
    sfx = suffix()
    net = d.network(f"a8-pgtest-{sfx}")
    pg = d.container(
        f"a8-pg-{sfx}",
        PG_IMAGE,
        "--network",
        net,
        "--network-alias",
        "postgres",
        "-e",
        "POSTGRES_USER=postgres",
        "-e",
        "POSTGRES_PASSWORD=su-" + sfx,
        "-e",
        "POSTGRES_DB=postgres",
        "-e",
        "HIBISCUS_DB_NAME=hibiscus",
        "-e",
        "HIBISCUS_DB_USER=hibiscus",
        "-e",
        f"HIBISCUS_DB_PASSWORD={APP_PASSWORD}",
        "-e",
        f"HIBISCUS_DB_MONITOR_PASSWORD={MON_PASSWORD}",
        "-e",
        "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256",
        "-v",
        f"{DEPLOY / 'postgres/initdb'}:/docker-entrypoint-initdb.d:ro",
    )
    try:
        # The image restarts postgres after running initdb scripts; wait for the final server
        # by connecting over TCP as the app role created by our script.
        d.wait_until(
            [
                "docker",
                "exec",
                "-e",
                f"PGPASSWORD={APP_PASSWORD}",
                pg,
                "psql",
                "-h",
                "127.0.0.1",
                "-U",
                "hibiscus",
                "-d",
                "hibiscus",
                "-c",
                "SELECT 1",
            ],
            timeout=120,
        )
        ddl = contract_ddl()
        run(
            [
                "docker",
                "exec",
                "-i",
                "-e",
                f"PGPASSWORD={APP_PASSWORD}",
                pg,
                "psql",
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                "127.0.0.1",
                "-U",
                "hibiscus",
                "-d",
                "hibiscus",
            ],
            input_text=ddl,
        )
        seed = """
        INSERT INTO workspaces (id, slug, name) VALUES (gen_random_uuid(), 'lab', 'Lab');
        INSERT INTO gpu_nodes (id, host, device_index, name, total_vram_mb, compute_capability,
                               supports_bf16, supports_fast_fp16, status, last_heartbeat_at)
        VALUES ('cuda0', 'gpu-box', 0, 'NVIDIA GeForce RTX 3060', 12288, '8.6', true, true, 'online', now()),
               ('cuda1', 'gpu-box', 1, 'Tesla P40', 24576, '6.1', false, false, 'offline', NULL);
        INSERT INTO jobs (id, workspace_id, kind, resource, status, payload)
        SELECT gen_random_uuid(), id, 'validate_dataset', 'cpu', 'queued', '{}'::jsonb
          FROM workspaces WHERE slug = 'lab';
        INSERT INTO jobs (id, workspace_id, kind, resource, status, payload)
        SELECT gen_random_uuid(), id, 'export_model', 'gpu', 'succeeded', '{}'::jsonb
          FROM workspaces WHERE slug = 'lab';
        """
        run(
            [
                "docker",
                "exec",
                "-i",
                "-e",
                f"PGPASSWORD={APP_PASSWORD}",
                pg,
                "psql",
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                "127.0.0.1",
                "-U",
                "hibiscus",
                "-d",
                "hibiscus",
            ],
            input_text=seed,
        )
        yield {"pg": pg, "net": net, "sfx": sfx, "backups": str(tmp_path_factory.mktemp("backups"))}
    finally:
        d.cleanup()


def psql(pg: str, user: str, password: str, sql: str, db: str = "hibiscus", check: bool = True) -> str:
    return run(
        [
            "docker",
            "exec",
            "-e",
            f"PGPASSWORD={password}",
            pg,
            "psql",
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            "127.0.0.1",
            "-U",
            user,
            "-d",
            db,
            "-c",
            sql,
        ],
        check=check,
    ).strip()


def test_app_role_is_not_superuser(stack: dict[str, str]) -> None:
    out = psql(
        stack["pg"],
        "hibiscus",
        APP_PASSWORD,
        "SELECT rolsuper, rolcreaterole FROM pg_roles WHERE rolname = 'hibiscus'",
    )
    assert out == "f|f"


def test_monitor_role_reads_aggregates_but_no_rows(stack: dict[str, str]) -> None:
    pg = stack["pg"]
    out = psql(
        pg,
        "hibiscus_monitor",
        MON_PASSWORD,
        "SELECT status || '=' || runs FROM monitoring.run_status_counts()",
    )
    statuses = dict(line.split("=") for line in out.splitlines())
    assert set(statuses) == {
        "queued",
        "preparing",
        "running",
        "pausing",
        "paused",
        "exporting",
        "succeeded",
        "failed",
        "cancelling",
        "cancelled",
    }
    assert all(v == "0" for v in statuses.values())
    queue = psql(
        pg,
        "hibiscus_monitor",
        MON_PASSWORD,
        "SELECT resource || '=' || queued FROM monitoring.job_queue() ORDER BY 1",
    )
    assert queue.splitlines() == ["cpu=1", "gpu=0"]
    nodes = psql(
        pg,
        "hibiscus_monitor",
        MON_PASSWORD,
        "SELECT node || ':' || online FROM monitoring.gpu_nodes() ORDER BY 1",
    )
    assert nodes.splitlines() == ["cuda0:1", "cuda1:0"]
    denied = subprocess.run(
        [
            "docker",
            "exec",
            "-e",
            f"PGPASSWORD={MON_PASSWORD}",
            pg,
            "psql",
            "-h",
            "127.0.0.1",
            "-U",
            "hibiscus_monitor",
            "-d",
            "hibiscus",
            "-c",
            "SELECT email FROM public.users",
        ],
        capture_output=True,
        text=True,
    )
    assert denied.returncode != 0
    assert "permission denied" in denied.stderr


def test_postgres_exporter_exposes_hibiscus_metrics(stack: dict[str, str]) -> None:
    d = Docker()
    try:
        exp = d.container(
            f"a8-pgexp-{stack['sfx']}",
            EXPORTER_IMAGE,
            "--network",
            stack["net"],
            "-e",
            "DATA_SOURCE_URI=postgres:5432/hibiscus?sslmode=disable",
            "-e",
            "DATA_SOURCE_USER=hibiscus_monitor",
            "-e",
            f"DATA_SOURCE_PASS={MON_PASSWORD}",
            "-v",
            f"{DEPLOY / 'observability/postgres-exporter'}:/etc/postgres-exporter:ro",
            cmd=["--extend.query-path=/etc/postgres-exporter/queries.yaml", "--no-collector.stat_bgwriter"],
        )
        metrics = ""
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            res = subprocess.run(
                ["docker", "exec", exp, "wget", "-qO-", "http://127.0.0.1:9187/metrics"],
                capture_output=True,
                text=True,
            )
            metrics = res.stdout
            if "hibiscus_gpu_node_online" in metrics:
                break
            time.sleep(1)
        assert re.search(r'^hibiscus_runs_runs\{.*status="queued".*\} 0$', metrics, re.M), d.logs(exp)[-2000:]
        assert re.search(r"^hibiscus_run_queue_queued(\{[^}]*\})? 0$", metrics, re.M)
        assert re.search(r'^hibiscus_job_queue_queued\{.*resource="cpu".*\} 1$', metrics, re.M)
        assert re.search(r'^hibiscus_gpu_node_online\{.*node="cuda0".*\} 1$', metrics, re.M)
        assert re.search(
            r'^hibiscus_jobs_jobs\{.*kind="export_model".*status="succeeded".*\} 1$', metrics, re.M
        )
        assert re.search(r"^pg_up(\{[^}]*\})? 1$", metrics, re.M)
    finally:
        d.cleanup()


def _backup(stack: dict[str, str], *extra_env: str, passphrase: str | None = PASSPHRASE) -> list[Path]:
    d = Docker()
    try:
        name = f"a8-backup-{stack['sfx']}-{suffix()}"
        key_env = ["-e", f"HIBISCUS_BACKUP_PASSPHRASE={passphrase}"] if passphrase is not None else []
        run(
            [
                "docker",
                "run",
                "--rm",
                "--name",
                name,
                "--network",
                stack["net"],
                "--label",
                "ai.hibiscus.test=a8",
                "-u",
                f"{os.getuid()}:{os.getgid()}",
                "-e",
                "PGHOST=postgres",
                "-e",
                "PGDATABASE=hibiscus",
                "-e",
                "PGUSER=hibiscus",
                "-e",
                f"PGPASSWORD={APP_PASSWORD}",
                "-e",
                "BACKUP_DIR=/backups",
                *key_env,
                *extra_env,
                "-v",
                f"{DEPLOY / 'backup'}:/backup:ro",
                "-v",
                f"{stack['backups']}:/backups",
                "--entrypoint",
                "/bin/bash",
                PG_IMAGE,
                "/backup/pg-backup.sh",
            ]
        )
    finally:
        d.cleanup()
    return sorted(Path(stack["backups"]).glob(DUMP_GLOB))


def test_backup_produces_verified_dump_and_prunes_old(stack: dict[str, str]) -> None:
    backups = Path(stack["backups"])
    stale = backups / "hibiscus-hibiscus-20200101T000000Z.dump"
    stale.write_bytes(b"old")
    (backups / (stale.name + ".sha256")).write_text("x")
    os.utime(stale, (time.time() - 40 * 86400, time.time() - 40 * 86400))
    dumps = _backup(stack, "-e", "BACKUP_RETENTION_DAYS=14")
    assert not stale.exists(), "dump older than retention must be pruned"
    assert len(dumps) == 1
    dump = dumps[0]
    assert dump.stat().st_size > 1000
    sha = Path(str(dump) + ".sha256").read_text()
    assert dump.name in sha
    subprocess.run(["sha256sum", "--check", "--status", dump.name + ".sha256"], cwd=backups, check=True)
    assert int((backups / "last-success").read_text()) > time.time() - 300
    # SEC-infra-2: what lands on the host is OpenPGP ciphertext, not a pg_dump archive ...
    head = dump.read_bytes()[:16]
    assert not head.startswith(b"PGDMP"), "backup is not encrypted"
    assert head[0] & 0x80, "not an OpenPGP packet"
    # ... and no plaintext dump is left anywhere in the backup directory.
    assert not [p for p in backups.iterdir() if p.name.endswith((".dump", ".partial"))]
    listed = subprocess.run(
        ["docker", "run", "--rm", "-i", "--entrypoint", "pg_restore", PG_IMAGE, "--list"],
        input=dump.read_bytes(),
        capture_output=True,
    )
    assert listed.returncode != 0, "pg_restore must not read the encrypted file without the key"


def test_backup_refuses_to_run_without_passphrase(stack: dict[str, str]) -> None:
    before = set(Path(stack["backups"]).iterdir())
    with pytest.raises(RuntimeError, match="HIBISCUS_BACKUP_PASSPHRASE"):
        _backup(stack, passphrase=None)
    with pytest.raises(RuntimeError, match="HIBISCUS_BACKUP_PASSPHRASE"):
        _backup(stack, passphrase="CHANGE_ME")  # noqa: S106 (placeholder must be refused)
    assert set(Path(stack["backups"]).iterdir()) == before, "nothing may be written unencrypted"


def _restore(stack: dict[str, str], dump: Path, *args: str) -> str:
    env = dict(
        os.environ,
        HIBISCUS_PG_EXEC=f"docker exec -i {stack['pg']}",
        HIBISCUS_BACKUP_PASSPHRASE=PASSPHRASE,
        HIBISCUS_ENV_FILE="/nonexistent",
    )
    res = subprocess.run(
        ["bash", str(DEPLOY / "backup/restore.sh"), str(dump), "--yes", *args],
        capture_output=True,
        text=True,
        env=env,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    return res.stdout


def test_restore_drill_into_scratch_database(stack: dict[str, str]) -> None:
    dump = sorted(Path(stack["backups"]).glob(DUMP_GLOB))[-1]
    out = _restore(stack, dump, "--target-db", "hibiscus_restore_drill")
    assert "checksum ok" in out and "decrypted ok" in out
    pg = stack["pg"]
    live = psql(pg, "hibiscus", APP_PASSWORD, "SELECT count(*) FROM pg_tables WHERE schemaname='public'")
    restored = psql(
        pg,
        "hibiscus",
        APP_PASSWORD,
        "SELECT count(*) FROM pg_tables WHERE schemaname='public'",
        db="hibiscus_restore_drill",
    )
    assert live == restored and int(live) >= 27
    assert psql(pg, "hibiscus", APP_PASSWORD, "SELECT count(*) FROM jobs", db="hibiscus_restore_drill") == "2"
    owner = psql(
        pg,
        "hibiscus",
        APP_PASSWORD,
        "SELECT tableowner FROM pg_tables WHERE tablename='runs'",
        db="hibiscus_restore_drill",
    )
    assert owner == "hibiscus"
    # monitoring functions + grants survive the round trip
    q = psql(
        pg,
        "hibiscus_monitor",
        MON_PASSWORD,
        "SELECT queued FROM monitoring.job_queue() WHERE resource='cpu'",
        db="hibiscus_restore_drill",
    )
    assert q == "1"


def test_in_place_restore_rolls_back_later_writes(stack: dict[str, str]) -> None:
    pg = stack["pg"]
    dump = sorted(Path(stack["backups"]).glob(DUMP_GLOB))[-1]
    psql(
        pg,
        "hibiscus",
        APP_PASSWORD,
        "INSERT INTO jobs (id, workspace_id, kind, resource, status, payload) "
        "SELECT gen_random_uuid(), id, 'merge_datasets', 'cpu', 'queued', '{}'::jsonb FROM workspaces",
    )
    assert psql(pg, "hibiscus", APP_PASSWORD, "SELECT count(*) FROM jobs") == "3"
    _restore(stack, dump, "--no-stop")
    assert psql(pg, "hibiscus", APP_PASSWORD, "SELECT count(*) FROM jobs") == "2"


def test_restore_rejects_tampered_dump(stack: dict[str, str], tmp_path: Path) -> None:
    dump = sorted(Path(stack["backups"]).glob(DUMP_GLOB))[-1]
    bad = tmp_path / dump.name
    bad.write_bytes(dump.read_bytes()[:-10] + b"0123456789")
    (tmp_path / (dump.name + ".sha256")).write_text(Path(str(dump) + ".sha256").read_text())
    env = dict(
        os.environ, HIBISCUS_PG_EXEC=f"docker exec -i {stack['pg']}", HIBISCUS_BACKUP_PASSPHRASE=PASSPHRASE
    )
    res = subprocess.run(
        ["bash", str(DEPLOY / "backup/restore.sh"), str(bad), "--yes", "--target-db", "x_tamper"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert res.returncode != 0
    assert "sha256 mismatch" in res.stderr
    # Even with a matching checksum file, the OpenPGP MDC rejects a modified ciphertext.
    (tmp_path / (dump.name + ".sha256")).write_text(
        subprocess.run(
            ["sha256sum", bad.name], cwd=tmp_path, check=True, capture_output=True, text=True
        ).stdout
    )
    res = subprocess.run(
        ["bash", str(DEPLOY / "backup/restore.sh"), str(bad), "--yes", "--target-db", "x_tamper"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert res.returncode != 0
    assert "cannot decrypt" in res.stderr


def test_restore_rejects_wrong_passphrase(stack: dict[str, str]) -> None:
    dump = sorted(Path(stack["backups"]).glob(DUMP_GLOB))[-1]
    env = dict(
        os.environ,
        HIBISCUS_PG_EXEC=f"docker exec -i {stack['pg']}",
        HIBISCUS_BACKUP_PASSPHRASE="wrong-passphrase-0123456789",  # noqa: S106
    )
    res = subprocess.run(
        ["bash", str(DEPLOY / "backup/restore.sh"), str(dump), "--yes", "--target-db", "x_wrongkey"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert res.returncode != 0
    assert "cannot decrypt" in res.stderr
    dbs = psql(stack["pg"], "hibiscus", APP_PASSWORD, "SELECT datname FROM pg_database")
    assert "x_wrongkey" not in dbs.split()


def _sh(cmd: list[str], env: dict[str, str]) -> str:
    res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    assert res.returncode == 0, res.stdout + res.stderr
    return res.stdout


def test_minio_mirror_is_encrypted_incremental_and_restorable(stack: dict[str, str], tmp_path: Path) -> None:
    """SEC-infra-2: the MinIO mirror destination holds only ciphertext; decrypt-tree restores it."""
    d = Docker()
    sfx = suffix()
    root_pw = "minio-" + sfx
    try:
        net = d.network(f"a8-mirror-{sfx}")
        minio = d.container(
            f"a8-minio-{sfx}",
            MINIO_IMAGE,
            "--network",
            net,
            "--network-alias",
            "minio",
            "-e",
            "MINIO_ROOT_USER=root",
            "-e",
            f"MINIO_ROOT_PASSWORD={root_pw}",
            cmd=["server", "/data"],
        )
        mc_host = f"http://root:{root_pw}@minio:9000"

        def mc(script: str) -> str:
            return run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    net,
                    "-e",
                    f"MC_HOST_lt={mc_host}",
                    "--entrypoint",
                    "sh",
                    MC_IMAGE,
                    "-c",
                    script,
                ]
            )

        d.wait_until(["docker", "exec", minio, "curl", "-fsS", "http://127.0.0.1:9000/minio/health/live"])
        secret_text = "very secret dataset row " + sfx
        mc(
            "set -e; mc mb -p lt/hibiscus-datasets lt/hibiscus-artifacts; "
            f"echo '{secret_text}' | mc pipe lt/hibiscus-datasets/ws/ds/v1/data/chunk-000.parquet; "
            "echo model | mc pipe lt/hibiscus-artifacts/runs/r1/model.zip; "
            "echo gone | mc pipe lt/hibiscus-artifacts/runs/r1/old.txt"
        )
        dest = tmp_path / "mirror"
        env = dict(
            os.environ,
            HIBISCUS_ENV_FILE="/nonexistent",
            HIBISCUS_S3_ACCESS_KEY="root",
            HIBISCUS_S3_SECRET_KEY=root_pw,
            HIBISCUS_BACKUP_PASSPHRASE=PASSPHRASE,
            HIBISCUS_MIRROR_NETWORK=net,
            HIBISCUS_MC_IMAGE=MC_IMAGE,
            HIBISCUS_POSTGRES_IMAGE=PG_IMAGE,
        )
        script = str(DEPLOY / "backup/minio-mirror.sh")
        out = _sh(["bash", script, str(dest)], env)
        assert "hibiscus-datasets: 1 encrypted" in out and "hibiscus-artifacts: 2 encrypted" in out, out
        files = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
        assert "hibiscus-datasets/ws/ds/v1/data/chunk-000.parquet.gpg" in files, files
        assert not [f for f in files if not f.endswith((".gpg", ".gpg.etag", "last-mirror"))], files
        for p in dest.rglob("*"):
            if p.is_file():
                assert secret_text.encode() not in p.read_bytes(), p
        # unchanged objects are not re-encrypted
        again = _sh(["bash", script, str(dest)], env)
        assert "hibiscus-datasets: 0 encrypted, 1 unchanged" in again, again
        # --remove drops objects deleted from MinIO
        mc("mc rm lt/hibiscus-artifacts/runs/r1/old.txt")
        pruned = _sh(["bash", script, str(dest), "--remove"], env)
        assert "hibiscus-artifacts: 0 encrypted, 1 unchanged, 1 removed" in pruned, pruned
        assert not (dest / "hibiscus-artifacts/runs/r1/old.txt.gpg").exists()
        # restore path
        plain = tmp_path / "plain"
        _sh(["bash", str(DEPLOY / "backup/decrypt-tree.sh"), str(dest), str(plain)], env)
        assert (plain / "hibiscus-datasets/ws/ds/v1/data/chunk-000.parquet").read_text() == secret_text + "\n"
        assert (plain / "hibiscus-artifacts/runs/r1/model.zip").read_text() == "model\n"
        # no passphrase -> no mirror at all
        env.pop("HIBISCUS_BACKUP_PASSPHRASE")
        res = subprocess.run(["bash", script, str(tmp_path / "m2")], env=env, capture_output=True, text=True)
        assert res.returncode != 0 and "HIBISCUS_BACKUP_PASSPHRASE" in res.stderr
    finally:
        d.cleanup()


def test_backup_health_script(stack: dict[str, str], tmp_path: Path) -> None:
    def health(last_age: int | None, started_age: int) -> int:
        script = (
            "set -e; mkdir -p /b; "
            + (f"echo $(( $(date +%s) - {last_age} )) > /b/last-success; " if last_age is not None else "")
            + f"echo $(( $(date +%s) - {started_age} )) > /tmp/backup-loop.started; "
            "BACKUP_DIR=/b bash /backup/backup-health.sh"
        )
        res = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{DEPLOY / 'backup'}:/backup:ro",
                "--entrypoint",
                "/bin/bash",
                PG_IMAGE,
                "-c",
                script,
            ],
            capture_output=True,
            text=True,
        )
        return res.returncode

    assert health(last_age=3600, started_age=7 * 86400) == 0  # recent backup
    assert health(last_age=30 * 3600, started_age=7 * 86400) == 1  # stale backup
    assert health(last_age=None, started_age=600) == 0  # just started, none yet
    assert health(last_age=None, started_age=2 * 86400) == 1  # running 2 days, never succeeded
