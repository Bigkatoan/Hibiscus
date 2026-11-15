"""Personal access tokens + shared dependencies (require_scope / require_role / ensure_role)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pyotp
import pytest
import sqlalchemy as sa
from fastapi import APIRouter, Depends

from app.core.deps import Principal, current_principal, ensure_role, require_role, require_scope
from app.db.models import ApiToken, PatScope, Session, WorkspaceRole
from tests.auth.fixtures import Ctx


def _probe_router() -> APIRouter:
    r = APIRouter(prefix="/api/v1/datasets")

    @r.get("")
    async def list_ds(p: Principal = Depends(require_scope(PatScope.DATASETS_READ))) -> dict[str, Any]:
        return {"items": [], "next_cursor": None}

    @r.post("", status_code=201)
    async def create_ds(
        p: Principal = Depends(require_scope(PatScope.DATASETS_WRITE)),
        _r: Principal = Depends(require_role("workspace_id", WorkspaceRole.MEMBER)),
    ) -> dict[str, Any]:
        return {"ok": True}

    return r


async def _pat(ctx: Ctx, api: Any, ws: uuid.UUID, scopes: list[str], **extra: Any) -> dict[str, Any]:
    r = await api.post(
        "/api/v1/auth/tokens", json={"name": "collector", "workspace_id": str(ws), "scopes": scopes, **extra}
    )
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


async def test_create_list_use_revoke_pat(ctx: Ctx) -> None:
    u = await ctx.create_user("pat@example.com")
    ws = await ctx.create_workspace("lab", {u.id: WorkspaceRole.MEMBER})
    api = ctx.client()
    await ctx.login(api, "pat@example.com")
    tok = await _pat(ctx, api, ws.id, ["datasets:write", "runs:read"])
    plain = tok["token"]
    assert plain.startswith(f"hbp_{tok['prefix']}_") and len(plain) == 4 + 8 + 1 + 43
    assert tok["expires_at"] is not None
    exp = datetime.fromisoformat(tok["expires_at"].replace("Z", "+00:00"))
    assert timedelta(days=89) < exp - datetime.now(UTC) <= timedelta(days=90)
    stored = await ctx.scalar(sa.select(ApiToken.token_hash).where(ApiToken.id == uuid.UUID(tok["id"])))
    assert plain.encode() not in stored and len(stored) == 32
    listed = (await api.get("/api/v1/auth/tokens")).json()["items"]
    assert [t["id"] for t in listed] == [tok["id"]] and "token" not in listed[0]

    bearer = ctx.client()
    h = {"Authorization": f"Bearer {plain}"}
    me = await bearer.get("/api/v1/auth/me", headers=h)
    assert me.status_code == 200
    body = me.json()
    assert body["auth_method"] == "pat" and body["token"]["id"] == tok["id"] and body["session_id"] is None
    assert [m["workspace_id"] for m in body["memberships"]] == [str(ws.id)]
    assert body["token"]["last_used_at"] is not None
    wss = await bearer.get("/api/v1/workspaces", headers=h)
    assert [w["id"] for w in wss.json()["items"]] == [str(ws.id)]
    # PATs cannot use /auth/* (except /auth/me), /admin, or cookie-only endpoints; no CSRF needed
    r = await bearer.http.get("/api/v1/auth/tokens", headers=h)
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    r = await bearer.http.get("/api/v1/admin/users", headers=h)
    assert r.status_code == 403
    r = await bearer.http.get(f"/api/v1/workspaces/{ws.id}/members", headers=h)
    assert r.status_code == 403 and r.json()["code"] == "forbidden"

    assert (await api.delete(f"/api/v1/auth/tokens/{tok['id']}")).status_code == 204
    assert (await api.delete(f"/api/v1/auth/tokens/{tok['id']}")).status_code == 204  # idempotent
    assert (await api.delete(f"/api/v1/auth/tokens/{uuid.uuid4()}")).status_code == 404
    r = await bearer.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 401 and r.json()["code"] == "token_revoked"


async def test_pat_validation_and_permissions(ctx: Ctx) -> None:
    secret = pyotp.random_base32(32)
    u = await ctx.create_user("viewer@example.com")
    owner = await ctx.create_user("own@example.com", totp_secret=secret)
    ws = await ctx.create_workspace("view", {u.id: WorkspaceRole.VIEWER, owner.id: WorkspaceRole.OWNER})
    other = await ctx.create_workspace("other", {owner.id: WorkspaceRole.OWNER})
    api = ctx.client()
    await ctx.login(api, "viewer@example.com")
    base = {"name": "x", "workspace_id": str(ws.id)}
    r = await api.post("/api/v1/auth/tokens", json={**base, "scopes": ["datasets:write"]})
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    r = await api.post("/api/v1/auth/tokens", json={**base, "scopes": []})
    assert r.status_code == 422
    r = await api.post("/api/v1/auth/tokens", json={**base, "scopes": ["runs:read", "runs:read"]})
    assert r.status_code == 422
    r = await api.post("/api/v1/auth/tokens", json={**base, "scopes": ["admin"]})
    assert r.status_code == 422
    r = await api.post("/api/v1/auth/tokens", json={**base, "scopes": ["runs:read"], "expires_in_days": 400})
    assert r.status_code == 422
    r = await api.post(
        "/api/v1/auth/tokens", json={"name": "x", "workspace_id": str(other.id), "scopes": ["runs:read"]}
    )
    assert r.status_code == 404
    tok = await _pat(ctx, api, ws.id, ["models:read"], expires_in_days=None)
    assert tok["expires_at"] is None
    # an owner with 2FA whose session is not MFA-verified must re-verify
    oapi = ctx.client()
    await ctx.login(oapi, "own@example.com", totp_secret=secret)
    await ctx.execute(sa.update(Session).where(Session.user_id == owner.id).values(mfa_verified=False))
    r = await oapi.post("/api/v1/auth/tokens", json={**base, "scopes": ["runs:read"]})
    assert r.status_code == 403 and r.json()["code"] == "mfa_reauth_required"


async def test_pat_expiry_membership_and_malformed(ctx: Ctx) -> None:
    u = await ctx.create_user("exp@example.com")
    ws = await ctx.create_workspace("exp", {u.id: WorkspaceRole.MEMBER})
    api = ctx.client()
    await ctx.login(api, "exp@example.com")
    tok = await _pat(ctx, api, ws.id, ["runs:read"])
    h = {"Authorization": f"Bearer {tok['token']}"}
    bearer = ctx.client()
    await ctx.execute(sa.update(ApiToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    r = await bearer.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 401 and r.json()["code"] == "token_expired"
    await ctx.execute(sa.update(ApiToken).values(expires_at=None))
    assert (await bearer.get("/api/v1/auth/me", headers=h)).status_code == 200
    # removing the membership makes the PAT unusable (and revokes it)
    from app.db.models import Membership

    await ctx.execute(sa.delete(Membership).where(Membership.user_id == u.id))
    r = await bearer.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 401 and r.json()["code"] == "token_revoked"
    for bad in ("hbp_short", "hbp_ABCDEFGH_" + "x" * 43, "not-a-pat"):
        r = await bearer.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401 and r.json()["code"] == "unauthenticated"


@pytest.fixture
async def probe(ctx: Ctx) -> Ctx:
    ctx.app.include_router(_probe_router())
    return ctx


async def test_require_scope_and_role(probe: Ctx) -> None:
    ctx = probe
    u = await ctx.create_user("scope@example.com")
    v = await ctx.create_user("viewer2@example.com")
    ws = await ctx.create_workspace("scope", {u.id: WorkspaceRole.MEMBER, v.id: WorkspaceRole.VIEWER})
    other = await ctx.create_workspace("scope-other", {u.id: WorkspaceRole.MEMBER})
    api = ctx.client(validate=False)
    await ctx.login(api, "scope@example.com")
    read = await _pat(ctx, api, ws.id, ["datasets:read"])
    write = await _pat(ctx, api, ws.id, ["datasets:write"])
    b = ctx.client(validate=False)
    hr = {"Authorization": f"Bearer {read['token']}"}
    hw = {"Authorization": f"Bearer {write['token']}"}
    assert (await b.http.get("/api/v1/datasets", headers=hr)).status_code == 200
    assert (await b.http.get("/api/v1/datasets", headers=hw)).status_code == 200  # write implies read
    r = await b.http.post(f"/api/v1/datasets?workspace_id={ws.id}", headers=hr)
    assert r.status_code == 403 and r.json()["code"] == "insufficient_scope"
    assert (await b.http.post(f"/api/v1/datasets?workspace_id={ws.id}", headers=hw)).status_code == 201
    r = await b.http.post(f"/api/v1/datasets?workspace_id={other.id}", headers=hw)
    assert r.status_code == 403 and r.json()["code"] == "forbidden"  # PAT bound to another workspace
    r = await b.http.post(f"/api/v1/datasets?workspace_id={uuid.uuid4()}", headers=hw)
    assert r.status_code == 403
    # session principal: role checks; non-member => 404, bad id => 404
    assert (await api.post(f"/api/v1/datasets?workspace_id={ws.id}")).status_code == 201
    assert (await api.post(f"/api/v1/datasets?workspace_id={uuid.uuid4()}")).status_code == 404
    assert (await api.post("/api/v1/datasets?workspace_id=nope")).status_code == 404
    vapi = ctx.client(validate=False)
    await ctx.login(vapi, "viewer2@example.com")
    r = await vapi.post(f"/api/v1/datasets?workspace_id={ws.id}")
    assert r.status_code == 403 and r.json()["code"] == "forbidden"


def test_ensure_role_matrix() -> None:
    ws = uuid.uuid4()
    ranks = [WorkspaceRole.VIEWER, WorkspaceRole.MEMBER, WorkspaceRole.ADMIN, WorkspaceRole.OWNER]
    from app.core.errors import ProblemError

    for i, have in enumerate(ranks):
        p = Principal(
            user_id=uuid.uuid4(),
            workspace_ids_roles={ws: have},
            auth_method="session",
            token_scopes=frozenset(),
            token_workspace_id=None,
            mfa_verified=True,
        )
        assert p.has_scope("anything")
        for j, need in enumerate(ranks):
            if i >= j:
                assert ensure_role(p, ws, need) == have
            else:
                with pytest.raises(ProblemError) as e:
                    ensure_role(p, ws, need)
                assert e.value.status == 403
        with pytest.raises(ProblemError) as e:
            ensure_role(p, uuid.uuid4(), WorkspaceRole.VIEWER)
        assert e.value.status == 404
    _ = current_principal
