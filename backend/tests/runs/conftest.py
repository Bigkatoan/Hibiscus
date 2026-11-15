"""Fixtures for the runs/models API: real Postgres 16, Redis 7, MinIO (testcontainers, random ports).

The app is the real ``app.main.create_app`` (core error handler, DB session, pagination, audit,
lifespan). These domain tests swap callers often, so ``app.core.deps.current_principal`` is
overridden with a mutable :class:`app.core.deps.Principal` (see :func:`make_principal`);
real cookie/PAT authentication of the same endpoints is covered by
``tests/integration/test_cross_domain_auth.py``. Everything else is real. Every JSON response
checked with :func:`check` is validated against ``api/openapi.yaml``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import boto3
import httpx
import pytest
import yaml
from fastapi import FastAPI
from jsonschema import Draft202012Validator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.deps import Principal, current_principal
from app.core.errors import ErrorCode, ProblemError
from app.core.settings import Settings
from app.db import models as m
from app.main import create_app
from app.runs.settings import RunsSettings

REPO = Path(__file__).resolve().parents[3]
OPENAPI = yaml.safe_load((REPO / "api" / "openapi.yaml").read_text())
GOLDEN = Path("~/datasets/robotics/so101_picknplace_20261114")
PG_IMAGE = "postgres:16.16-trixie"
REDIS_IMAGE = "redis:7.4.12-alpine"
MINIO_IMAGE = "pgsty/minio:RELEASE.2026-08-04T00-00-00Z"


# ------------------------------------------------------------------------------------------------
# OpenAPI response validation
# ------------------------------------------------------------------------------------------------
def _schema_for(path: str, method: str, status: int, ctype: str) -> dict[str, Any] | None:
    op = OPENAPI["paths"][path][method.lower()]
    resp = op["responses"].get(str(status))
    if resp is None:
        raise AssertionError(f"{method} {path}: status {status} not in contract")
    if "$ref" in resp:
        resp = OPENAPI["components"]["responses"][resp["$ref"].rsplit("/", 1)[-1]]
    content = resp.get("content", {})
    if not content:
        return None
    media = content.get(ctype) or next(iter(content.values()))
    schema: dict[str, Any] | None = media.get("schema")
    return schema


def check(resp: httpx.Response, path: str, method: str = "GET") -> Any:
    """Assert the response status/body conform to the contract; return the parsed JSON."""
    ctype = resp.headers.get("content-type", "").split(";")[0]
    schema = _schema_for(path, method, resp.status_code, ctype)
    if schema is None or not ctype.endswith("json"):
        return None
    body = resp.json()
    doc = {**schema, "components": OPENAPI["components"]}
    errs = sorted(Draft202012Validator(doc).iter_errors(body), key=lambda e: list(e.path))
    if errs:
        raise AssertionError(
            f"{method} {path} -> {resp.status_code} violates contract:\n"
            + "\n".join(f"  {list(e.absolute_path)}: {e.message[:300]}" for e in errs[:10])
        )
    return body


def problem(resp: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert resp.status_code == status, (resp.status_code, resp.text[:500])
    body = resp.json()
    doc = {"$ref": "#/components/schemas/Problem", "components": OPENAPI["components"]}
    Draft202012Validator(doc).validate(body)
    assert body["code"] == code, body
    return dict(body)


# ------------------------------------------------------------------------------------------------
# services
# ------------------------------------------------------------------------------------------------
@dataclass
class Services:
    pg_sync: str
    pg_async: str
    redis_url: str
    s3_endpoint: str
    s3_key: str
    s3_secret: str


@pytest.fixture(scope="session")
def services() -> Iterator[Services]:
    from testcontainers.minio import MinioContainer
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    pg = PostgresContainer(
        PG_IMAGE,
        username="hibiscus",
        password="hibiscus",
        dbname="hibiscus",
        driver="psycopg",
    )
    rd = RedisContainer(REDIS_IMAGE)
    mn = MinioContainer(MINIO_IMAGE)
    for c in (pg, rd, mn):
        c.start()
    try:
        sync = pg.get_connection_url()
        cfg = mn.get_config()
        svc = Services(
            pg_sync=sync,
            pg_async=sync.replace("postgresql+psycopg://", "postgresql+asyncpg://"),
            redis_url=f"redis://{rd.get_container_host_ip()}:{rd.get_exposed_port(6379)}/0",
            s3_endpoint=f"http://{cfg['endpoint']}",
            s3_key=cfg["access_key"],
            s3_secret=cfg["secret_key"],
        )
        eng = create_engine(sync)
        m.Base.metadata.create_all(eng)
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO roles (name, rank, requires_mfa, description) VALUES ('owner',40,true,'o'),"
                    "('admin',30,true,'a'),('member',20,false,'m'),('viewer',10,false,'v')"
                )
            )
        eng.dispose()
        s3 = boto3.client(
            "s3",
            endpoint_url=svc.s3_endpoint,
            aws_access_key_id=svc.s3_key,
            aws_secret_access_key=svc.s3_secret,
            region_name="us-east-1",
        )
        for b in ("hibiscus-artifacts", "hibiscus-datasets", "hibiscus-uploads"):
            s3.create_bucket(Bucket=b)
        yield svc
    finally:
        for c in (mn, rd, pg):
            c.stop()


@pytest.fixture
def sync_engine(services: Services) -> Iterator[Any]:
    eng = create_engine(services.pg_sync)
    with eng.begin() as conn:
        conn.execute(text("UPDATE gpu_nodes SET current_run_id = NULL"))
        conn.execute(text("UPDATE datasets SET latest_version_id = NULL"))
        conn.execute(
            text(
                "TRUNCATE gpu_telemetry, run_metrics, run_events, models, checkpoints, jobs, resource_estimates, "  # noqa: E501
                "notifications, gpu_nodes, runs, dataset_versions, datasets, quotas, memberships, workspaces, "  # noqa: E501
                "user_secrets, users CASCADE"
            )
        )
    yield eng
    eng.dispose()


def golden_features() -> dict[str, Any]:
    if (GOLDEN / "meta" / "info.json").exists():
        return dict(json.loads((GOLDEN / "meta" / "info.json").read_text())["features"])
    return {
        "action": {"dtype": "float32", "shape": [6]},
        "observation.state": {"dtype": "float32", "shape": [6]},
        "observation.images.wrist_cam": {"dtype": "video", "shape": [360, 640, 3]},
    }


@dataclass
class World:
    user_id: uuid.UUID
    other_user_id: uuid.UUID
    workspace_id: uuid.UUID
    other_workspace_id: uuid.UUID
    dataset_id: uuid.UUID
    version_id: uuid.UUID
    principal: Principal
    extra: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def world(sync_engine: Any) -> World:
    uid, uid2, wid, wid2, did, vid = (uuid.uuid4() for _ in range(6))
    with Session(sync_engine) as s:
        s.add_all(
            [
                m.User(id=uid, email=f"a{uid.hex[:6]}@x.io", display_name="Alice", password_hash="x"),
                m.User(id=uid2, email=f"b{uid2.hex[:6]}@x.io", display_name="Bob", password_hash="x"),
                m.Workspace(id=wid, slug=f"ws-{wid.hex[:8]}", name="Lab"),
                m.Workspace(id=wid2, slug=f"ws-{wid2.hex[:8]}", name="Other"),
            ]
        )
        s.flush()
        s.add_all(
            [
                m.Membership(workspace_id=wid, user_id=uid, role=m.WorkspaceRole.MEMBER),
                m.Membership(workspace_id=wid, user_id=uid2, role=m.WorkspaceRole.ADMIN),
                m.Membership(workspace_id=wid2, user_id=uid2, role=m.WorkspaceRole.OWNER),
                m.Dataset(
                    id=did,
                    workspace_id=wid,
                    name="so101_picknplace_20261114",
                    slug="so101_picknplace_20261114",
                ),
            ]
        )
        s.flush()
        feats = golden_features()
        s.add(
            m.DatasetVersion(
                id=vid,
                dataset_id=did,
                version=1,
                status=m.DatasetVersionStatus.READY,
                source=m.DatasetSource.UPLOAD,
                content_hash="a" * 64,
                storage_prefix=f"s3://hibiscus-datasets/{wid}/{did}/1/",
                total_episodes=20,
                total_frames=11277,
                features=feats,
                camera_keys=["observation.images.wrist_cam"],
                fps=30.0,
            )
        )
        s.add_all(
            [
                m.GpuNode(
                    id="cuda0",
                    host="box",
                    device_index=0,
                    name="NVIDIA GeForce RTX 3060",
                    total_vram_mb=12288,
                    compute_capability="8.6",
                    supports_bf16=True,
                    supports_fast_fp16=True,
                    status=m.GpuNodeStatus.ONLINE,
                ),
                m.GpuNode(
                    id="cuda1",
                    host="box",
                    device_index=1,
                    name="Tesla P40",
                    total_vram_mb=24576,
                    compute_capability="6.1",
                    supports_bf16=False,
                    supports_fast_fp16=False,
                    status=m.GpuNodeStatus.ONLINE,
                ),
            ]
        )
        s.commit()
    p = make_principal(user_id=uid, workspace_ids_roles={wid: "member"})
    return World(uid, uid2, wid, wid2, did, vid, p)


def make_principal(
    *,
    user_id: uuid.UUID,
    workspace_ids_roles: dict[uuid.UUID, str],
    auth_method: str = "session",
    token_scopes: frozenset[str] = frozenset(),
    token_workspace_id: uuid.UUID | None = None,
    mfa_verified: bool = False,
    is_platform_admin: bool = False,
) -> Principal:
    """A core ``Principal`` with test-friendly defaults (roles given as strings)."""
    return Principal(
        user_id=user_id,
        workspace_ids_roles={k: m.WorkspaceRole(v) for k, v in workspace_ids_roles.items()},
        auth_method="pat" if auth_method == "pat" else "session",
        token_scopes=token_scopes,
        token_workspace_id=token_workspace_id,
        mfa_verified=mfa_verified,
        is_platform_admin=is_platform_admin,
    )


class PrincipalHolder:
    def __init__(self) -> None:
        self.p: Principal | None = None

    async def __call__(self) -> Principal:
        if self.p is None:
            raise ProblemError(401, ErrorCode.UNAUTHENTICATED, "no principal")
        return self.p


@pytest.fixture
def holder(world: World) -> PrincipalHolder:
    h = PrincipalHolder()
    h.p = world.principal
    return h


def runs_settings(**over: Any) -> RunsSettings:
    base: dict[str, Any] = {"run_reaper": False, "sse_heartbeat_s": 1.0, "sse_poll_s": 0.5}
    base.update(over)
    return RunsSettings(**base)


def core_settings(services: Services) -> Settings:
    return Settings(
        env="test",
        database_url=services.pg_async,
        redis_url=services.redis_url,
        s3_endpoint_url=services.s3_endpoint,
        s3_access_key=services.s3_key,
        s3_secret_key=services.s3_secret,
        argon2_time_cost=1,
        argon2_memory_cost_kib=8,
        argon2_parallelism=1,
        log_level="WARNING",
        public_base_url="https://robot.example.com",
        trusted_proxy_cidrs=["127.0.0.0/8"],
    )


def make_app(holder: PrincipalHolder, services: Services, **runs_over: Any) -> FastAPI:
    """The real app (default ``extra_routers``) with the caller injected through ``holder``."""
    app = create_app(core_settings(services))
    app.state.runs.settings = runs_settings(**runs_over)
    app.dependency_overrides[current_principal] = holder
    return app


@pytest.fixture
async def client(
    services: Services, holder: PrincipalHolder, world: World
) -> AsyncIterator[httpx.AsyncClient]:
    app = make_app(holder, services)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
            c.app = app  # type: ignore[attr-defined]
            yield c


def run_body(world: World, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "workspace_id": str(world.workspace_id),
        "dataset_version_id": str(world.version_id),
        "policy_type": "act",
        "preset": "quick",
        "config": {
            "policy": {"chunk_size": 50, "n_action_steps": 50},
            "train": {"steps": 300, "save_freq": 100},
        },
        "gpu": "cuda0",
    }
    body.update(over)
    return body
