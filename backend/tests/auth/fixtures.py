"""Shared integration fixtures for tests/auth and tests/workspaces (real Postgres 16, Redis 7, MinIO).

Containers are started once per test session (module-level singleton, random host ports) and torn
down at exit. Each test gets a fresh app (NullPool engine) and truncated tables.
"""

from __future__ import annotations

import asyncio
import atexit
import os
import re
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from pyotp.totp import TOTP
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

from testcontainers.minio import MinioContainer
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from app.core.settings import Settings
from app.db.models import Base, Membership, Role, User, Workspace, WorkspaceRole
from app.main import create_app
from tests.auth.openapi_check import validate_response

PG_IMAGE = os.environ.get("HIBISCUS_TEST_PG_IMAGE", "postgres:16.16-trixie")
REDIS_IMAGE = os.environ.get("HIBISCUS_TEST_REDIS_IMAGE", "redis:7.4.12-alpine")
MINIO_IMAGE = os.environ.get("HIBISCUS_TEST_MINIO_IMAGE", "pgsty/minio:RELEASE.2026-08-04T00-00-00Z")
PASSWORD = "Correct-Horse-Battery-9"
BASE = "https://testserver"


@dataclass
class Infra:
    pg_url: str
    redis_url: str
    s3_endpoint: str
    s3_access: str
    s3_secret: str
    _containers: list[Any] = field(default_factory=list)


_infra: Infra | None = None


def _start() -> Infra:
    pg = PostgresContainer(PG_IMAGE, username="hibiscus", password="hibiscus", dbname="hibiscus", driver=None)
    rd = RedisContainer(REDIS_IMAGE)
    mn = MinioContainer(MINIO_IMAGE)
    for c in (pg, rd, mn):
        c.start()
    host = pg.get_container_host_ip()
    pg_url = f"postgresql+asyncpg://hibiscus:hibiscus@{host}:{pg.get_exposed_port(5432)}/hibiscus"
    redis_url = f"redis://{rd.get_container_host_ip()}:{rd.get_exposed_port(6379)}/0"
    mcfg = mn.get_config()
    infra = Infra(
        pg_url=pg_url,
        redis_url=redis_url,
        s3_endpoint=f"http://{mcfg['endpoint']}",
        s3_access=mcfg["access_key"],
        s3_secret=mcfg["secret_key"],
        _containers=[pg, rd, mn],
    )
    asyncio.run(_init_schema(pg_url))

    def _stop() -> None:
        for c in infra._containers:
            try:
                c.stop()
            except Exception:  # noqa: S110 - best-effort teardown
                pass

    atexit.register(_stop)
    return infra


AUDIT_TRIGGER = """
CREATE OR REPLACE FUNCTION audit_events_immutable() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit_events is append-only'; END $$ LANGUAGE plpgsql;
"""
AUDIT_TRIGGER_BIND = """
CREATE TRIGGER audit_events_immutable BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();
"""


async def _init_schema(url: str) -> None:
    eng = create_async_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(sa.text(AUDIT_TRIGGER))
        await conn.execute(sa.text(AUDIT_TRIGGER_BIND))
    await eng.dispose()


def infra() -> Infra:
    global _infra
    if _infra is None:
        _infra = _start()
    return _infra


ROLES = [
    (WorkspaceRole.OWNER, 40, True, "Owner"),
    (WorkspaceRole.ADMIN, 30, True, "Admin"),
    (WorkspaceRole.MEMBER, 20, False, "Member"),
    (WorkspaceRole.VIEWER, 10, False, "Viewer"),
]


async def reset_db(url: str) -> None:
    eng = create_async_engine(url)
    tables = [t.name for t in reversed(Base.metadata.sorted_tables) if t.name != "roles"]
    async with eng.begin() as conn:
        await conn.execute(
            sa.text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE")
        )
        n = (await conn.execute(sa.text("SELECT count(*) FROM roles"))).scalar_one()
        if not n:
            for name, rank, mfa, desc in ROLES:
                await conn.execute(
                    sa.insert(Role).values(name=name, rank=rank, requires_mfa=mfa, description=desc)
                )
    await eng.dispose()


def make_settings(**overrides: Any) -> Settings:
    i = infra()
    base: dict[str, Any] = {
        "env": "test",
        "database_url": i.pg_url,
        "redis_url": i.redis_url,
        "s3_endpoint_url": i.s3_endpoint,
        "s3_access_key": i.s3_access,
        "s3_secret_key": i.s3_secret,
        "argon2_time_cost": 1,
        "argon2_memory_cost_kib": 8,
        "argon2_parallelism": 1,
        "log_json": True,
        "log_level": "WARNING",
        "public_base_url": "https://robot.example.com",
        "trusted_proxy_cidrs": ["127.0.0.0/8"],
        "extra_routers": [],
    }
    base.update(overrides)
    return Settings(**base)


class Api:
    """httpx client bound to the ASGI app; validates every response against api/openapi.yaml."""

    def __init__(self, app: Any, *, validate: bool = True, client_ip: str = "127.0.0.1") -> None:
        self.app = app
        hooks = {"response": [self._check]} if validate else {}
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(client_ip, 50000)),
            base_url=BASE,
            event_hooks=hooks,
        )

    async def _check(self, response: httpx.Response) -> None:
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            return
        await response.aread()
        validate_response(response.request.method, response.request.url.path, response)

    def csrf(self) -> dict[str, str]:
        tok = self.http.cookies.get("hb_csrf")
        return {"X-CSRF-Token": tok} if tok else {}

    async def get(self, url: str, **kw: Any) -> httpx.Response:
        return await self.http.get(url, **kw)

    async def post(self, url: str, csrf: bool = True, **kw: Any) -> httpx.Response:
        headers = {**(self.csrf() if csrf else {}), **kw.pop("headers", {})}
        return await self.http.post(url, headers=headers, **kw)

    async def patch(self, url: str, **kw: Any) -> httpx.Response:
        headers = {**self.csrf(), **kw.pop("headers", {})}
        return await self.http.patch(url, headers=headers, **kw)

    async def put(self, url: str, **kw: Any) -> httpx.Response:
        headers = {**self.csrf(), **kw.pop("headers", {})}
        return await self.http.put(url, headers=headers, **kw)

    async def delete(self, url: str, **kw: Any) -> httpx.Response:
        headers = {**self.csrf(), **kw.pop("headers", {})}
        return await self.http.delete(url, headers=headers, **kw)

    async def aclose(self) -> None:
        await self.http.aclose()


@dataclass
class Ctx:
    app: Any
    settings: Settings
    clients: list[Api] = field(default_factory=list)

    def client(self, **kw: Any) -> Api:
        c = Api(self.app, **kw)
        self.clients.append(c)
        return c

    @property
    def svc(self) -> Any:
        return self.app.state.services

    def session(self) -> AsyncSession:
        sm = self.svc.db.sessionmaker
        s: AsyncSession = sm()
        return s

    async def create_user(
        self,
        email: str,
        *,
        password: str = PASSWORD,
        display_name: str | None = None,
        platform_admin: bool = False,
        totp_secret: str | None = None,
        active: bool = True,
    ) -> User:
        from app.auth import mfa

        async with self.session() as s:
            u = User(
                email=email.lower(),
                display_name=display_name or email.split("@")[0].title(),
                password_hash=self.svc.passwords.hash(password),
                email_verified_at=datetime.now(UTC),
                is_platform_admin=platform_admin,
                is_active=active,
            )
            s.add(u)
            await s.flush()
            if totp_secret:
                u.totp_secret_enc = mfa.encrypt_secret(self.svc.cipher, u.id, totp_secret)
                u.totp_enabled_at = datetime.now(UTC)
            await s.commit()
            await s.refresh(u)
            return u

    async def create_workspace(self, slug: str, members: dict[uuid.UUID, WorkspaceRole]) -> Workspace:
        async with self.session() as s:
            ws = Workspace(slug=slug, name=slug.replace("-", " ").title(), settings={})
            s.add(ws)
            await s.flush()
            for uid, role in members.items():
                s.add(Membership(workspace_id=ws.id, user_id=uid, role=role))
            await s.commit()
            await s.refresh(ws)
            return ws

    async def reset_totp_step(self, user_id: uuid.UUID) -> None:
        async with self.session() as s:
            await s.execute(sa.update(User).where(User.id == user_id).values(totp_last_used_step=None))
            await s.commit()

    async def scalar(self, stmt: Any) -> Any:
        async with self.session() as s:
            return (await s.execute(stmt)).scalar()

    async def execute(self, stmt: Any) -> None:
        async with self.session() as s:
            await s.execute(stmt)
            await s.commit()

    async def login(
        self, api: Api, email: str, password: str = PASSWORD, totp_secret: str | None = None
    ) -> httpx.Response:
        r = await api.post("/api/v1/auth/login", csrf=False, json={"email": email, "password": password})
        if r.status_code == 200 and r.json()["status"] == "mfa_required":
            assert totp_secret, "user has 2FA; pass totp_secret"
            uid = await self.scalar(sa.select(User.id).where(User.email == email.lower()))
            await self.reset_totp_step(uid)
            r = await api.post(
                "/api/v1/auth/login/2fa",
                csrf=False,
                json={"mfa_token": r.json()["mfa_token"], "code": TOTP(totp_secret).now()},
            )
        return r


@pytest.fixture(scope="session")
def containers() -> Iterator[Infra]:
    yield infra()


@pytest.fixture
async def ctx(containers: Infra) -> AsyncIterator[Ctx]:
    await reset_db(containers.pg_url)
    settings = make_settings()
    app = create_app(settings)
    await app.state.services.redis.flushdb()
    c = Ctx(app=app, settings=settings)
    yield c
    await _close(c)


async def _close(c: Ctx) -> None:
    from app.core.events import drain_pending_publishes

    for cl in c.clients:
        await cl.aclose()
    await drain_pending_publishes()
    try:
        await c.app.state.services.redis.aclose()
    except Exception:  # noqa: S110
        pass
    await c.app.state.services.db.dispose()


@pytest.fixture
async def make_ctx(containers: Infra) -> AsyncIterator[Any]:
    """Factory for an app with custom settings (DB is reset on each call)."""
    created: list[Ctx] = []

    async def _make(**overrides: Any) -> Ctx:
        await reset_db(containers.pg_url)
        settings = make_settings(**overrides)
        app = create_app(settings)
        try:
            await app.state.services.redis.flushdb()
        except Exception:  # noqa: S110 - some tests point redis at a dead port on purpose
            pass
        c = Ctx(app=app, settings=settings)
        created.append(c)
        return c

    yield _make
    for c in created:
        await _close(c)


TOKEN_RE = re.compile(r"token=([A-Za-z0-9_-]{32,128})")


def token_from(text: str) -> str:
    m = TOKEN_RE.search(text)
    assert m, text
    return m.group(1)
