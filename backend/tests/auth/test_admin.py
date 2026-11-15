"""/admin/* (users, audit log, quotas, system), Cloudflare Access gate, bootstrap CLI."""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt as pyjwt
import pyotp
import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives.asymmetric import rsa

from app.admin.bootstrap import bootstrap, main
from app.auth.cf_access import CfAccessVerifier
from app.core.audit import verify_chain
from app.core.errors import ProblemError
from app.db.models import ApiToken, AuditEvent, GpuNode, Session, User, WorkspaceRole
from tests.auth.fixtures import PASSWORD, Ctx, token_from

SECRET = pyotp.random_base32(32)


async def _admin(ctx: Ctx) -> tuple[User, Any]:
    u = await ctx.create_user(
        "root@example.com", platform_admin=True, totp_secret=SECRET, display_name="Root"
    )
    api = ctx.client()
    r = await ctx.login(api, u.email, totp_secret=SECRET)
    assert r.status_code == 200
    return u, api


async def test_admin_requires_platform_admin_and_mfa(ctx: Ctx) -> None:
    await ctx.create_user("plain@example.com")
    api = ctx.client()
    await ctx.login(api, "plain@example.com")
    assert (await api.get("/api/v1/admin/users")).status_code == 403
    root, rapi = await _admin(ctx)
    assert (await rapi.get("/api/v1/admin/users")).status_code == 200
    await ctx.execute(sa.update(Session).where(Session.user_id == root.id).values(mfa_verified=False))
    r = await rapi.get("/api/v1/admin/users")
    assert r.status_code == 403 and r.json()["code"] == "mfa_reauth_required"
    # platform admin without TOTP => enrolment gate
    await ctx.create_user("newadmin@example.com", platform_admin=True)
    napi = ctx.client()
    assert (await ctx.login(napi, "newadmin@example.com")).json()["mfa_enrollment_required"] is True
    assert (await napi.get("/api/v1/admin/users")).json()["code"] == "mfa_enrollment_required"


async def test_list_users_search_and_pagination(ctx: Ctx) -> None:
    root, api = await _admin(ctx)
    for i in range(5):
        await ctx.create_user(f"user{i}@example.com", display_name=f"User {i}")
    await ctx.create_user("odd_%name@example.com", display_name="Percent")
    ws = await ctx.create_workspace("www", {root.id: WorkspaceRole.OWNER})
    seen: list[str] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"limit": 3}
        if cursor:
            params["cursor"] = cursor
        r = await api.get("/api/v1/admin/users", params=params)
        assert r.status_code == 200
        seen += [u["email"] for u in r.json()["items"]]
        cursor = r.json()["next_cursor"]
        if not cursor:
            break
    assert seen == sorted(seen) and len(seen) == 7
    root_row = next(u for u in (await api.get("/api/v1/admin/users", params={"q": "ROOT"})).json()["items"])
    assert root_row["workspaces"][0]["workspace_id"] == str(ws.id) and root_row["is_active"] is True
    r = await api.get("/api/v1/admin/users", params={"q": "%"})
    assert [u["email"] for u in r.json()["items"]] == ["odd_%name@example.com"]
    r = await api.get("/api/v1/admin/users", params={"cursor": "tampered.cursor"})
    assert r.status_code == 400 and r.json()["code"] == "bad_request"


async def test_update_user(ctx: Ctx) -> None:
    root, api = await _admin(ctx)
    t = await ctx.create_user("target@example.com")
    tapi = ctx.client()
    await ctx.login(tapi, t.email)
    url = f"/api/v1/admin/users/{t.id}"
    # adminUpdateUser documents no 422: validation failures are 400 bad_request (CR-A2-5)
    assert (await api.patch(url, json={})).status_code == 400
    assert (await api.patch(url, json={"unlock": False})).json()["code"] == "bad_request"
    assert (await api.patch(f"/api/v1/admin/users/{uuid.uuid4()}", json={"unlock": True})).status_code == 404
    r = await api.patch(url, json={"is_platform_admin": True})
    assert r.status_code == 409 and r.json()["code"] == "mfa_required_by_role"
    await ctx.execute(
        sa.update(User)
        .where(User.id == t.id)
        .values(failed_login_count=7, locked_until=datetime.now(UTC) + timedelta(hours=1))
    )
    r = await api.patch(url, json={"unlock": True})
    assert r.status_code == 200 and r.json()["locked_until"] is None
    r = await api.patch(url, json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert (await tapi.get("/api/v1/auth/me")).status_code == 401
    assert (await ctx.login(ctx.client(), t.email)).json()["code"] == "account_disabled"
    assert (await api.patch(url, json={"is_active": True})).json()["is_active"] is True
    r = await api.patch(f"/api/v1/admin/users/{root.id}", json={"is_active": False})
    assert r.status_code == 409
    r = await api.patch(f"/api/v1/admin/users/{root.id}", json={"is_platform_admin": False})
    assert r.status_code == 409  # last platform admin
    assert (await api.patch(f"/api/v1/admin/users/{root.id}", json={"reset_mfa": True})).status_code == 409
    # grant admin to a 2FA user, then reset their MFA
    secret2 = pyotp.random_base32(32)
    t2 = await ctx.create_user("t2@example.com", totp_secret=secret2)
    r = await api.patch(f"/api/v1/admin/users/{t2.id}", json={"is_platform_admin": True})
    assert r.status_code == 200 and r.json()["is_platform_admin"] is True
    r = await api.patch(f"/api/v1/admin/users/{t2.id}", json={"reset_mfa": True})
    assert r.status_code == 200 and r.json()["mfa_enabled"] is False
    r = await api.patch(f"/api/v1/admin/users/{root.id}", json={"is_platform_admin": False})
    assert r.status_code == 200
    n = await ctx.scalar(
        sa.select(sa.func.count()).select_from(AuditEvent).where(AuditEvent.action == "admin.user_updated")
    )
    assert n == 6


async def test_revoke_sessions_and_reset_link(ctx: Ctx) -> None:
    _root, api = await _admin(ctx)
    t = await ctx.create_user("victim@example.com")
    ws = await ctx.create_workspace("vvv", {t.id: WorkspaceRole.MEMBER})
    tapi = ctx.client()
    await ctx.login(tapi, t.email)
    pat = await tapi.post(
        "/api/v1/auth/tokens", json={"name": "p", "workspace_id": str(ws.id), "scopes": ["runs:read"]}
    )
    assert (await api.post(f"/api/v1/admin/users/{t.id}/revoke-sessions")).status_code == 204
    assert (await tapi.get("/api/v1/auth/me")).status_code == 401
    assert await ctx.scalar(sa.select(ApiToken.revoked_at).where(ApiToken.id == uuid.UUID(pat.json()["id"])))
    assert (await api.post(f"/api/v1/admin/users/{uuid.uuid4()}/revoke-sessions")).status_code == 404
    r = await api.post(f"/api/v1/admin/users/{t.id}/password-reset-link")
    assert r.status_code == 201
    url = r.json()["url"]
    assert url.startswith("https://robot.example.com/reset-password#token=")
    anon = ctx.client()
    ok = await anon.post(
        "/api/v1/auth/password/reset",
        csrf=False,
        json={"token": token_from(url), "new_password": "Admin-Reset-Pass-1"},
    )
    assert ok.status_code == 204
    assert (await ctx.login(ctx.client(), t.email, "Admin-Reset-Pass-1")).status_code == 200


async def test_audit_log_listing_filters_and_chain(ctx: Ctx) -> None:
    root, api = await _admin(ctx)
    for _ in range(3):
        await ctx.client().post(
            "/api/v1/auth/login", csrf=False, json={"email": "x@example.com", "password": "nope"}
        )
    r = await api.get("/api/v1/admin/audit-events", params={"limit": 2})
    assert r.status_code == 200
    page1 = r.json()
    assert len(page1["items"]) == 2 and page1["next_cursor"]
    ids = [e["id"] for e in page1["items"]]
    assert ids == sorted(ids, reverse=True)
    page2 = (
        await api.get("/api/v1/admin/audit-events", params={"limit": 2, "cursor": page1["next_cursor"]})
    ).json()
    assert all(e["id"] < ids[-1] for e in page2["items"])
    failed = (await api.get("/api/v1/admin/audit-events", params={"action": "auth.login_failed"})).json()[
        "items"
    ]
    assert len(failed) == 3 and all(e["outcome"] == "failure" and e["actor"] is None for e in failed)
    assert all(e["ip"] == "127.0.0.1" and e["request_id"] for e in failed)
    mine = (await api.get("/api/v1/admin/audit-events", params={"actor_user_id": str(root.id)})).json()[
        "items"
    ]
    assert {e["action"] for e in mine} == {"auth.login"} and mine[0]["actor"]["display_name"] == "Root"
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    assert (await api.get("/api/v1/admin/audit-events", params={"since": future})).json()["items"] == []
    assert len((await api.get("/api/v1/admin/audit-events", params={"until": future})).json()["items"]) == 4
    assert (await api.get("/api/v1/admin/audit-events", params={"workspace_id": str(uuid.uuid4())})).json()[
        "items"
    ] == []
    assert (await api.get("/api/v1/admin/audit-events", params={"action": "nope"})).status_code == 400
    # immutability: DB trigger refuses UPDATE / DELETE; the hash chain verifies
    with pytest.raises(Exception, match="append-only"):
        await ctx.execute(sa.update(AuditEvent).values(outcome="success"))
    with pytest.raises(Exception, match="append-only"):
        await ctx.execute(sa.delete(AuditEvent))
    async with ctx.session() as s:
        assert await verify_chain(s, batch=2) == (True, None)


async def test_audit_chain_detects_tampering(ctx: Ctx) -> None:
    await ctx.client().post(
        "/api/v1/auth/login", csrf=False, json={"email": "x@example.com", "password": "nope"}
    )
    await ctx.client().post(
        "/api/v1/auth/login", csrf=False, json={"email": "y@example.com", "password": "nope"}
    )
    async with ctx.session() as s:
        await s.execute(sa.text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_immutable"))
        await s.execute(sa.update(AuditEvent).where(AuditEvent.id == 1).values(details={"forged": True}))
        await s.execute(sa.text("ALTER TABLE audit_events ENABLE TRIGGER audit_events_immutable"))
        await s.commit()
    async with ctx.session() as s:
        assert await verify_chain(s) == (False, 1)


async def test_quotas(ctx: Ctx) -> None:
    root, api = await _admin(ctx)
    m = await ctx.create_user("m@example.com")
    outsider = await ctx.create_user("o@example.com")
    ws = await ctx.create_workspace("qqq", {root.id: WorkspaceRole.OWNER, m.id: WorkspaceRole.MEMBER})
    url = f"/api/v1/admin/workspaces/{ws.id}/quotas"
    assert (await api.get(url)).json() == {"items": []}
    limits = {
        "max_concurrent_runs": 2,
        "max_queued_runs": 4,
        "gpu_hours_per_month": 12.5,
        "storage_bytes": 10**11,
        "max_upload_bytes": 10**9,
    }
    r = await api.put(url, json={"user_id": None, **limits})
    assert r.status_code == 200 and r.json()["user_id"] is None and r.json()["gpu_hours_per_month"] == 12.5
    r2 = await api.put(url, json={"user_id": None, **{**limits, "max_concurrent_runs": 3}})
    assert r2.json()["id"] == r.json()["id"] and r2.json()["max_concurrent_runs"] == 3
    r = await api.put(url, json={"user_id": str(m.id), **limits})
    assert r.status_code == 200 and r.json()["user_id"] == str(m.id)
    r = await api.put(url, json={"user_id": str(outsider.id), **limits})
    assert r.status_code == 422
    r = await api.put(url, json={"user_id": None, **{**limits, "max_concurrent_runs": -1}})
    assert r.status_code == 422
    r = await api.put(url, json=limits)
    assert r.status_code == 422  # user_id is required (nullable)
    items = (await api.get(url)).json()["items"]
    assert [i["user_id"] for i in items] == [None, str(m.id)]
    assert (await api.get(f"/api/v1/admin/workspaces/{uuid.uuid4()}/quotas")).status_code == 404


async def test_system_status(ctx: Ctx) -> None:
    _root, api = await _admin(ctx)
    await ctx.svc.s3.ensure_buckets()
    await ctx.svc.s3.put_object("hibiscus-artifacts", "x/y.bin", b"12345")
    async with ctx.session() as s:
        s.add(
            GpuNode(
                id="cuda0",
                host="h",
                device_index=0,
                name="NVIDIA GeForce RTX 3060",
                total_vram_mb=12288,
                compute_capability="8.6",
                supports_bf16=True,
                supports_fast_fp16=True,
            )
        )
        await s.commit()
    r = await api.get("/api/v1/admin/system")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["api_version"] == "0.1.0" and body["lerobot_version"] == "0.7.1" and body["queue_depth"] == 0
    assert body["gpus"][0]["id"] == "cuda0" and body["gpus"][0]["status"] == "offline"
    assert body["storage"]["buckets"]["hibiscus-artifacts"] == 5 and body["storage"]["disk_free_bytes"] > 0
    assert body["email"] == {"provider": "none", "enabled": False}


# ---------------------------------------------------------------------------------------------
# Cloudflare Access
# ---------------------------------------------------------------------------------------------
def _rsa_jwks() -> tuple[Any, dict[str, Any]]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": "k1", "alg": "RS256", "use": "sig"})
    return key, {"keys": [jwk]}


def _assertion(
    key: Any,
    *,
    aud: str = "aud-tag",
    iss: str = "https://team.cloudflareaccess.com",
    kid: str = "k1",
    exp: int | None = None,
) -> str:
    now = int(time.time())
    payload = {
        "aud": [aud],
        "iss": iss,
        "email": "root@example.com",
        "iat": now,
        "exp": exp or now + 300,
        "sub": "x",
    }
    return pyjwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


async def test_cf_access_verifier_unit() -> None:
    key, jwks = _rsa_jwks()
    calls = 0

    async def fetch() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return jwks

    v = CfAccessVerifier("https://team.cloudflareaccess.com/", "aud-tag", fetch_jwks=fetch)
    claims = await v.verify_token(_assertion(key))
    assert claims["email"] == "root@example.com"
    await v.verify_token(_assertion(key))
    assert calls == 1  # cached
    other_key, _ = _rsa_jwks()
    for bad in (
        _assertion(other_key),
        _assertion(key, aud="other"),
        _assertion(key, iss="https://evil.example.com"),
        _assertion(key, exp=int(time.time()) - 3600),
        _assertion(key, kid="unknown"),
        "not-a-jwt",
    ):
        with pytest.raises(ProblemError) as e:
            await v.verify_token(bad)
        assert e.value.status == 403


async def test_cf_access_gate_on_admin_routes(make_ctx: Any) -> None:
    key, jwks = _rsa_jwks()

    async def fetch() -> dict[str, Any]:
        return jwks

    ctx: Ctx = await make_ctx(cf_access_team_domain="team.cloudflareaccess.com", cf_access_aud="aud-tag")
    ctx.svc.cf_access = CfAccessVerifier("team.cloudflareaccess.com", "aud-tag", fetch_jwks=fetch)
    _root, api = await _admin(ctx)
    r = await api.get("/api/v1/admin/users")
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    r = await api.get("/api/v1/admin/users", headers={"Cf-Access-Jwt-Assertion": _assertion(key)})
    assert r.status_code == 200
    # non-admin API is unaffected by the Access gate
    assert (await api.get("/api/v1/auth/me")).status_code == 200


# ---------------------------------------------------------------------------------------------
# Bootstrap CLI
# ---------------------------------------------------------------------------------------------
async def test_bootstrap_creates_first_admin_once(ctx: Ctx) -> None:
    code, link = await bootstrap(ctx.settings, "First.Admin@Example.com", "First", 60)
    assert code == 0 and link.startswith("https://robot.example.com/reset-password#token=")
    user = await ctx.scalar(sa.select(User).where(User.email == "first.admin@example.com"))
    assert user.is_platform_admin and user.email_verified_at is not None
    # the random initial password is unusable; the link sets a real one
    api = ctx.client()
    r = await api.post(
        "/api/v1/auth/password/reset",
        csrf=False,
        json={"token": token_from(link), "new_password": "Bootstrap-Pass-2026"},
    )
    assert r.status_code == 204
    login = await ctx.login(api, "first.admin@example.com", "Bootstrap-Pass-2026")
    assert login.json()["mfa_enrollment_required"] is True
    code, msg = await bootstrap(ctx.settings, "second@example.com", "Second", 60)
    assert code == 2 and "already exists" in msg
    code, msg = await bootstrap(ctx.settings, "first.admin@example.com", "First", 60, reissue=True)
    assert code == 2  # already logged in
    code, msg = await bootstrap(ctx.settings, "not-an-email", "X", 60)
    assert code == 1


async def test_bootstrap_reissue_and_cli(
    ctx: Ctx, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    await ctx.create_user("exists@example.com")
    code, msg = await bootstrap(ctx.settings, "exists@example.com", "X", 60)
    assert code == 2 and "already exists" in msg
    code, first = await bootstrap(ctx.settings, "boot@example.com", "Boot", 30)
    assert code == 0
    code, second = await bootstrap(ctx.settings, "boot@example.com", "Boot", 30, reissue=True)
    assert code == 0 and second != first
    anon = ctx.client()
    r = await anon.post(
        "/api/v1/auth/password/reset",
        csrf=False,
        json={"token": token_from(first), "new_password": "Bootstrap-Pass-2026"},
    )
    assert r.status_code == 400  # superseded by the reissued link
    import app.admin.bootstrap as mod

    monkeypatch.setattr(mod, "get_settings", lambda: ctx.settings)

    async def fake_run(coro: Any) -> Any:
        return await coro

    # run main() in a worker thread with its own event loop (main uses asyncio.run)
    import asyncio

    rc = await asyncio.to_thread(main, ["--email", "boot@example.com", "--reissue"])
    out = capsys.readouterr()
    assert rc == 0 and "reset-password#token=" in out.out
    rc = await asyncio.to_thread(main, ["--email", "x@example.com"])
    assert rc == 2 and "error:" in capsys.readouterr().err
    _ = (fake_run, PASSWORD)
