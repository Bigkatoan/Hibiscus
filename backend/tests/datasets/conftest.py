"""Fixtures: the real app (``app.main.create_app``) on the shared test infrastructure of
``tests/auth/fixtures.py`` (Postgres 16, Redis 7, MinIO; random host ports), with real
authentication: actors carry a cookie session (``Actor.h``) or a PAT (``await Actor.pat(...)``)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
import httpx
import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.core.storage import BUCKET_DATASETS, BUCKET_UPLOADS
from app.db.models import WorkspaceRole
from app.main import create_app
from tests.auth.fixtures import infra, make_settings, reset_db
from tests.integration.authn import add_member, create_user, create_workspace, pat_headers, session_headers

REPO = Path(__file__).resolve().parents[3]
DEFAULT_EXTRA_ROUTERS: list[str] = Settings.model_fields["extra_routers"].get_default(
    call_default_factory=True
)


@dataclass
class Services:
    pg_url_async: str
    pg_url_sync: str
    s3_endpoint: str
    s3_key: str
    s3_secret: str


@pytest.fixture(scope="session")
def services() -> Iterator[Services]:
    i = infra()
    s3 = boto3.client(
        "s3",
        endpoint_url=i.s3_endpoint,
        aws_access_key_id=i.s3_access,
        aws_secret_access_key=i.s3_secret,
        region_name="us-east-1",
    )
    existing = {b["Name"] for b in s3.list_buckets().get("Buckets", [])}
    for b in (BUCKET_UPLOADS, BUCKET_DATASETS):
        if b not in existing:
            s3.create_bucket(Bucket=b)
    yield Services(
        pg_url_async=i.pg_url,
        pg_url_sync=i.pg_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"),
        s3_endpoint=i.s3_endpoint,
        s3_key=i.s3_access,
        s3_secret=i.s3_secret,
    )


@pytest.fixture
def s3_sync(services: Services) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=services.s3_endpoint,
        aws_access_key_id=services.s3_key,
        aws_secret_access_key=services.s3_secret,
        region_name="us-east-1",
    )


@pytest.fixture
async def app(services: Services) -> AsyncIterator[Any]:
    await reset_db(services.pg_url_async)  # truncates and seeds ``roles``
    application = create_app(make_settings(extra_routers=DEFAULT_EXTRA_ROUTERS))
    yield application
    await application.state.services.redis.aclose()
    await application.state.services.db.dispose()


@pytest.fixture
def sm(app: Any) -> async_sessionmaker[AsyncSession]:
    maker: async_sessionmaker[AsyncSession] = app.state.services.db.sessionmaker
    return maker


@pytest.fixture
async def client(app: Any) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver/api/v1") as c:
        yield c


@dataclass
class Actor:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    h: dict[str, str]  # cookie session + CSRF headers
    app: Any

    async def pat(self, scopes: str, workspace_id: uuid.UUID | None = None) -> dict[str, str]:
        """A PAT with comma-separated ``scopes`` bound to ``workspace_id`` (default: own workspace).

        A real PAT must belong to a member of its workspace, so the actor is added (as member) to
        ``workspace_id`` when needed (the workspace is created if it does not exist).
        """
        ws = workspace_id or self.workspace_id
        if ws != self.workspace_id:
            await add_member(self.app, ws, self.user_id, WorkspaceRole.MEMBER)
        return await pat_headers(self.app, self.user_id, ws, [s for s in scopes.split(",") if s])


@pytest.fixture
async def make_actor(app: Any) -> Any:
    async def _make(
        role: WorkspaceRole = WorkspaceRole.OWNER, workspace_id: uuid.UUID | None = None
    ) -> Actor:
        uid = await create_user(app)
        if workspace_id is None:
            workspace_id = await create_workspace(app, {uid: role})
        else:
            await add_member(app, workspace_id, uid, role)
        return Actor(uid, workspace_id, await session_headers(app, uid), app)

    return _make


# --------------------------------------------------------------------------------------------------
# OpenAPI response validation (the contract is the source of truth)
# --------------------------------------------------------------------------------------------------
_SPEC = yaml.safe_load((REPO / "api" / "openapi.yaml").read_text())
_REGISTRY: Registry = Registry().with_resource("urn:openapi", Resource.from_contents(_SPEC, DRAFT202012))


def _resolve(node: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        ref = node["$ref"]
        cur: Any = _SPEC
        for part in ref.removeprefix("#/").split("/"):
            cur = cur[part]
        node = cur
    return node


def assert_contract(resp: httpx.Response, path: str, method: str = "get") -> None:
    """Validate status + JSON body of ``resp`` against ``api/openapi.yaml`` for ``method path``."""
    op = _SPEC["paths"][path][method]
    responses = op["responses"]
    code = str(resp.status_code)
    assert code in responses, f"{method.upper()} {path}: status {code} not in contract {list(responses)}"
    r = _resolve(responses[code])
    content = r.get("content") or {}
    if not content:
        return
    ctype = resp.headers.get("content-type", "").split(";")[0]
    if ctype not in ("application/json", "application/problem+json"):
        return
    media = content.get(ctype) or content.get("application/json") or content.get("application/problem+json")
    assert media is not None, f"{ctype} not declared for {code}"
    schema = media.get("schema", {})
    pointer = schema.get("$ref")
    root: dict[str, Any] = {"$ref": "urn:openapi" + pointer} if pointer else schema
    v = Draft202012Validator(root, registry=_REGISTRY, format_checker=FormatChecker())
    errors = sorted(v.iter_errors(resp.json()), key=lambda e: list(e.path))
    assert not errors, (
        f"{method.upper()} {path} {code}: "
        + "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])
        + "\n"
        + json.dumps(resp.json())[:1500]
    )
