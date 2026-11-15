"""SEC-auth-01 residual (docs/security/phase5-reverify.md N2): PATs vs 2FA.

* enabling 2FA revokes every PAT of the user (they were minted without 2FA);
* an owner/admin PAT can only be minted from a 2FA-verified session;
* a PAT acts with owner/admin power only while the user has 2FA enabled *and* it was minted from
  a 2FA-verified session; otherwise it is capped at member.
"""

from __future__ import annotations

import uuid
from typing import Any

import pyotp
import pytest
import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pyotp.totp import TOTP

from app.core.deps import Principal, require_role
from app.db.models import ApiToken, Membership, User, WorkspaceRole
from tests.auth.fixtures import PASSWORD, Ctx


def _admin_probe() -> APIRouter:
    r = APIRouter(prefix="/api/v1/p5b-probe")

    @r.get("/{workspace_id}/admin")
    async def admin_only(
        p: Principal = Depends(require_role("workspace_id", WorkspaceRole.ADMIN)),
    ) -> dict[str, Any]:
        return {"ok": True}

    return r


@pytest.fixture
async def probe(ctx: Ctx) -> Ctx:
    ctx.app.include_router(_admin_probe())
    return ctx


async def _mint(api: Any, ws: uuid.UUID) -> dict[str, Any]:
    r = await api.post(
        "/api/v1/auth/tokens",
        json={"name": "collector", "workspace_id": str(ws), "scopes": ["runs:write", "datasets:write"]},
    )
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


async def test_enable_totp_revokes_pats_minted_before(ctx: Ctx) -> None:
    u = await ctx.create_user("pat2fa@example.com")
    ws = await ctx.create_workspace("lab", {u.id: WorkspaceRole.MEMBER})
    stolen, device = ctx.client(), ctx.client()
    await ctx.login(stolen, u.email)
    await ctx.login(device, u.email)
    tok = await _mint(stolen, ws.id)
    bearer = ctx.client()
    h = {"Authorization": f"Bearer {tok['token']}"}
    assert (await bearer.get("/api/v1/auth/me", headers=h)).status_code == 200

    secret = (await device.post("/api/v1/auth/2fa/totp/setup", json={"password": PASSWORD})).json()["secret"]
    r = await device.post("/api/v1/auth/2fa/totp/enable", json={"code": TOTP(secret).now()})
    assert r.status_code == 200, r.text
    assert r.json()["api_tokens_revoked"] == 1
    r = await bearer.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 401 and r.json()["code"] == "token_revoked"
    # a PAT minted afterwards from the 2FA-verified session works and is marked verified
    fresh = await _mint(device, ws.id)
    r = await bearer.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fresh['token']}"})
    assert r.status_code == 200
    assert await ctx.scalar(sa.select(ApiToken.mfa_verified).where(ApiToken.id == uuid.UUID(fresh["id"])))


async def test_pat_of_promoted_user_without_2fa_is_capped_at_member(probe: Ctx) -> None:
    ctx = probe
    u = await ctx.create_user("promo@example.com")
    ws = await ctx.create_workspace("lab", {u.id: WorkspaceRole.MEMBER})
    api = ctx.client()
    await ctx.login(api, u.email)
    tok = await _mint(api, ws.id)
    h = {"Authorization": f"Bearer {tok['token']}"}
    # the owner promotes the user to admin; the user has not enrolled in 2FA yet
    await ctx.execute(
        sa.update(Membership)
        .where(Membership.user_id == u.id, Membership.workspace_id == ws.id)
        .values(role=WorkspaceRole.ADMIN)
    )
    bearer = ctx.client(validate=False)
    r = await bearer.get(f"/api/v1/p5b-probe/{ws.id}/admin", headers=h)
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    # even with 2FA enabled later (e.g. set directly, without enableTotp revoking the PAT) the
    # PAT was minted without 2FA and stays capped
    await ctx.execute(sa.update(User).where(User.id == u.id).values(totp_enabled_at=sa.func.now()))
    r = await bearer.get(f"/api/v1/p5b-probe/{ws.id}/admin", headers=h)
    assert r.status_code == 403
    # still usable for member-level work
    assert (await bearer.get("/api/v1/auth/me", headers=h)).status_code == 200


async def test_admin_pat_needs_verified_session_and_2fa_at_use(probe: Ctx) -> None:
    ctx = probe
    secret = pyotp.random_base32(32)
    u = await ctx.create_user("adm@example.com", totp_secret=secret)
    ws = await ctx.create_workspace("ops", {u.id: WorkspaceRole.ADMIN})
    api = ctx.client()
    await ctx.login(api, u.email, totp_secret=secret)
    tok = await _mint(api, ws.id)
    h = {"Authorization": f"Bearer {tok['token']}"}
    bearer = ctx.client(validate=False)
    assert (await bearer.get(f"/api/v1/p5b-probe/{ws.id}/admin", headers=h)).status_code == 200
    # 2FA switched off (e.g. by a platform admin reset): the PAT loses admin power at once
    await ctx.execute(sa.update(User).where(User.id == u.id).values(totp_enabled_at=None))
    assert (await bearer.get(f"/api/v1/p5b-probe/{ws.id}/admin", headers=h)).status_code == 403


async def test_admin_cannot_mint_pat_without_verified_session(ctx: Ctx) -> None:
    from app.db.models import Session as DbSession

    secret = pyotp.random_base32(32)
    u = await ctx.create_user("adm2@example.com", totp_secret=secret)
    ws = await ctx.create_workspace("ops", {u.id: WorkspaceRole.OWNER})
    api = ctx.client()
    await ctx.login(api, u.email, totp_secret=secret)
    await ctx.execute(sa.update(DbSession).values(mfa_verified=False))
    r = await api.post(
        "/api/v1/auth/tokens",
        json={"name": "x", "workspace_id": str(ws.id), "scopes": ["runs:read"]},
    )
    assert r.status_code == 403 and r.json()["code"] == "mfa_reauth_required"
