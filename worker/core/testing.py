"""Pytest fixtures: real Postgres 16 / Redis 7 / MinIO via testcontainers (random host ports).

The schema is created from the frozen contract models (``backend/app/db/models.py``), so every
worker SQL statement is exercised against the real tables. Import in a conftest with
``from core.testing import *  # noqa: F403``.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, text

REPO = Path(__file__).resolve().parents[2]
PG_IMAGE = "postgres:16.16-trixie"
REDIS_IMAGE = "redis:7.4.12-alpine"
MINIO_IMAGE = "pgsty/minio:RELEASE.2026-08-04T00-00-00Z"


def contract_metadata() -> Any:
    backend = str(REPO / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    import importlib

    return importlib.import_module("app.db.models")


@dataclass
class Services:
    pg_url: str  # postgresql+psycopg://
    redis_url: str
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str


@pytest.fixture(scope="session")
def services() -> Iterator[Services]:
    from testcontainers.minio import MinioContainer
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    pg = PostgresContainer(
        PG_IMAGE,
        username="hibiscus",
        password="hibiscus",  # noqa: S106 - throwaway test container
        dbname="hibiscus",
        driver="psycopg",
    )
    rd = RedisContainer(REDIS_IMAGE)
    mn = MinioContainer(MINIO_IMAGE)
    pg.start()
    rd.start()
    mn.start()
    try:
        cfg = mn.get_config()
        svc = Services(
            pg_url=pg.get_connection_url(),
            redis_url=f"redis://{rd.get_container_host_ip()}:{rd.get_exposed_port(6379)}/0",
            s3_endpoint=f"http://{cfg['endpoint']}",
            s3_access_key=cfg["access_key"],
            s3_secret_key=cfg["secret_key"],
        )
        models = contract_metadata()
        eng = create_engine(svc.pg_url)
        models.Base.metadata.create_all(eng)
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO roles (name, rank, requires_mfa, description) VALUES "
                    "('owner',40,true,'owner'),('admin',30,true,'admin'),('member',20,false,'member'),"
                    "('viewer',10,false,'viewer')"
                )
            )
        eng.dispose()
        import boto3

        s3 = boto3.client(
            "s3",
            endpoint_url=svc.s3_endpoint,
            aws_access_key_id=svc.s3_access_key,
            aws_secret_access_key=svc.s3_secret_key,
            region_name="us-east-1",
        )
        for b in ("hibiscus-artifacts", "hibiscus-datasets", "hibiscus-uploads"):
            s3.create_bucket(Bucket=b)
        yield svc
    finally:
        mn.stop()
        rd.stop()
        pg.stop()


TRUNCATE_SQL = text(
    "TRUNCATE gpu_telemetry, run_metrics, run_events, models, checkpoints, jobs, resource_estimates, "
    "notifications, gpu_nodes, runs, dataset_versions, datasets, quotas, memberships, workspaces, users CASCADE"  # noqa: E501
)


@pytest.fixture
def engine(services: Services) -> Iterator[Engine]:
    eng = create_engine(services.pg_url)
    with eng.begin() as conn:
        conn.execute(text("UPDATE gpu_nodes SET current_run_id = NULL"))
        conn.execute(text("UPDATE datasets SET latest_version_id = NULL"))
        conn.execute(TRUNCATE_SQL)
    yield eng
    eng.dispose()


@dataclass
class Seed:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    dataset_id: uuid.UUID
    version_id: uuid.UUID


def seed_basic(
    engine: Engine,
    *,
    storage_prefix: str | None = None,
    content_hash: str | None = None,
    features: dict[str, Any] | None = None,
    slug: str = "golden",
    total_episodes: int = 20,
) -> Seed:
    m = contract_metadata()
    from sqlalchemy.orm import Session

    uid, wid, did, vid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with Session(engine) as s:
        s.add(m.User(id=uid, email=f"u{uid.hex[:8]}@example.com", display_name="Tester", password_hash="x"))  # noqa: S106
        s.add(m.Workspace(id=wid, slug=f"ws-{wid.hex[:8]}", name="WS"))
        s.flush()
        s.add(m.Membership(workspace_id=wid, user_id=uid, role=m.WorkspaceRole.OWNER))
        s.add(m.Dataset(id=did, workspace_id=wid, name=slug, slug=slug, created_by=uid))
        s.flush()
        s.add(
            m.DatasetVersion(
                id=vid,
                dataset_id=did,
                version=1,
                status=m.DatasetVersionStatus.READY,
                source=m.DatasetSource.UPLOAD,
                content_hash=content_hash or "0" * 64,
                storage_prefix=storage_prefix or f"s3://hibiscus-datasets/{wid}/{did}/1/",
                total_episodes=total_episodes,
                features=features or {"action": {"dtype": "float32", "shape": [6]}},
                camera_keys=["observation.images.wrist_cam"],
            )
        )
        s.commit()
    return Seed(uid, wid, did, vid)


def insert_run(engine: Engine, seed: Seed, **kw: Any) -> uuid.UUID:
    m = contract_metadata()
    from sqlalchemy.orm import Session

    rid: uuid.UUID = kw.pop("id", uuid.uuid4())
    with Session(engine) as s:
        number = kw.pop("number", None) or (
            s.execute(
                text("SELECT coalesce(max(number),0)+1 FROM runs WHERE workspace_id=:w"),
                {"w": seed.workspace_id},
            ).scalar_one()
        )
        run = m.Run(
            id=rid,
            workspace_id=seed.workspace_id,
            number=number,
            name=kw.pop("name", f"run-{number}"),
            created_by=kw.pop("created_by", seed.user_id),
            dataset_version_id=seed.version_id,
            policy_type=kw.pop("policy_type", "act"),
            config=kw.pop(
                "config", {"policy": {}, "train": {"steps": 100, "save_freq": 100, "log_freq": 10}}
            ),
            resolved_args=kw.pop("resolved_args", ["lerobot-train"]),
            heldout_episodes=kw.pop("heldout_episodes", [0]),
            train_episodes=kw.pop("train_episodes", list(range(1, 20))),
            seed=kw.pop("seed", 1000),
            total_steps=kw.pop("total_steps", 100),
            **kw,
        )
        s.add(run)
        s.commit()
    return rid
