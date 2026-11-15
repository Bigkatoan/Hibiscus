"""Login, lockout, 2FA login, refresh rotation + reuse detection, logout, /auth/me, /auth/config."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pyotp
import sqlalchemy as sa
from pyotp.totp import TOTP

from app.db.models import AuditEvent, Session, User, WorkspaceRole
from tests.auth.fixtures import PASSWORD, Ctx


async def test_healthz_and_config(ctx: Ctx) -> None:
    api = ctx.client()
    r = await api.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert r.headers["x-frame-options"] == "DENY"
    assert "max-age=" in r.headers["strict-transport-security"]
    assert r.headers["x-content-type-options"] == "nosniff"
    r = await api.get("/api/v1/auth/config")
    assert r.json() == {
        "turnstile_site_key": None,
        "email_delivery_enabled": False,
        "password_min_length": 12,
        "supported_locales": ["vi", "en"],
    }
    assert r.headers["cache-control"] == "no-store"


async def test_login_success_sets_cookies_and_me(ctx: Ctx) -> None:
    u = await ctx.create_user("alice@example.com")
    api = ctx.client()
    r = await ctx.login(api, "ALICE@example.com")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (
        body["status"] == "ok"
        and body["user"]["id"] == str(u.id)
        and body["mfa_enrollment_required"] is False
    )
    set_cookie = r.headers.get_list("set-cookie")
    access = next(c for c in set_cookie if c.startswith("hb_access="))
    refresh = next(c for c in set_cookie if c.startswith("hb_refresh="))
    csrf = next(c for c in set_cookie if c.startswith("hb_csrf="))
    for c in (access, refresh):
        assert "HttpOnly" in c and "Secure" in c and "SameSite=strict" in c
    assert "Path=/api" in access and "Path=/api/v1/auth" in refresh
    assert "HttpOnly" not in csrf and "Path=/" in csrf
    me = await api.get("/api/v1/auth/me")
    assert me.status_code == 200
    data = me.json()
    assert data["auth_method"] == "session" and data["user"]["email"] == "alice@example.com"
    assert data["memberships"] == [] and data["token"] is None and data["session_id"]
    events = await ctx.scalar(
        sa.select(sa.func.count()).select_from(AuditEvent).where(AuditEvent.action == "auth.login")
    )
    assert events == 1


async def test_login_wrong_password_and_unknown_email_are_identical(ctx: Ctx) -> None:
    await ctx.create_user("bob@example.com")
    api = ctx.client()
    r1 = await api.post(
        "/api/v1/auth/login", csrf=False, json={"email": "bob@example.com", "password": "nope-nope-nope"}
    )
    r2 = await api.post(
        "/api/v1/auth/login", csrf=False, json={"email": "nobody@example.com", "password": "nope-nope-nope"}
    )
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["code"] == r2.json()["code"] == "invalid_credentials"
    assert r1.json()["title"] == r2.json()["title"]
    assert r1.headers["content-type"].startswith("application/problem+json")
    assert r1.json()["request_id"] == r1.headers["x-request-id"]
    failed = await ctx.scalar(
        sa.select(sa.func.count()).select_from(AuditEvent).where(AuditEvent.action == "auth.login_failed")
    )
    assert failed == 2


async def test_lockout_after_five_failures_with_backoff(ctx: Ctx) -> None:
    u = await ctx.create_user("carol@example.com")
    api = ctx.client()
    bad = {"email": "carol@example.com", "password": "wrong-password-x"}
    for _ in range(4):
        r = await api.post("/api/v1/auth/login", csrf=False, json=bad)
        assert r.json()["code"] == "invalid_credentials"
    r = await api.post("/api/v1/auth/login", csrf=False, json=bad)
    # Locked, but the answer is the same 401 as for a wrong password / unknown email (SEC-auth-06)
    assert r.status_code == 401 and r.json()["code"] == "invalid_credentials"
    assert "retry-after" not in r.headers
    # even the correct password is refused while locked (and does not extend the lock)
    r = await api.post(
        "/api/v1/auth/login", csrf=False, json={"email": "carol@example.com", "password": PASSWORD}
    )
    assert r.status_code == 401 and r.json()["code"] == "invalid_credentials"
    assert await ctx.scalar(sa.select(User.failed_login_count).where(User.id == u.id)) == 5
    locked = await ctx.scalar(sa.select(User.locked_until).where(User.id == u.id))
    first = locked - datetime.now(UTC)
    assert timedelta(seconds=50) < first <= timedelta(seconds=61)
    # lock expires -> next failure doubles the lock
    await ctx.execute(
        sa.update(User).where(User.id == u.id).values(locked_until=datetime.now(UTC) - timedelta(seconds=1))
    )
    r = await api.post("/api/v1/auth/login", csrf=False, json=bad)
    assert r.status_code == 401
    locked2 = await ctx.scalar(sa.select(User.locked_until).where(User.id == u.id))
    assert locked2 - datetime.now(UTC) > timedelta(seconds=110)
    # success after expiry resets the counter
    await ctx.execute(sa.update(User).where(User.id == u.id).values(locked_until=None))
    r = await ctx.login(api, "carol@example.com")
    assert r.status_code == 200
    assert await ctx.scalar(sa.select(User.failed_login_count).where(User.id == u.id)) == 0
    assert (
        await ctx.scalar(
            sa.select(sa.func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "auth.account_locked")
        )
        == 2
    )


async def test_disabled_account(ctx: Ctx) -> None:
    await ctx.create_user("dave@example.com", active=False)
    api = ctx.client()
    r = await ctx.login(api, "dave@example.com")
    assert r.status_code == 403 and r.json()["code"] == "account_disabled"


async def test_login_validation_errors(ctx: Ctx) -> None:
    api = ctx.client()
    r = await api.post(
        "/api/v1/auth/login", csrf=False, json={"email": "x@example.com", "password": "p", "extra": 1}
    )
    assert r.status_code == 400 and r.json()["code"] == "bad_request"  # login documents no 422
    assert any(e["loc"][-1] == "extra" for e in r.json()["errors"])
    r = await api.post(
        "/api/v1/auth/login", csrf=False, content=b"{not json", headers={"content-type": "application/json"}
    )
    assert r.status_code == 400 and r.json()["code"] == "bad_request"


async def test_two_factor_login_and_recovery_code(ctx: Ctx) -> None:
    secret = pyotp.random_base32(32)
    u = await ctx.create_user("erin@example.com", totp_secret=secret)
    api = ctx.client()
    r = await api.post(
        "/api/v1/auth/login", csrf=False, json={"email": "erin@example.com", "password": PASSWORD}
    )
    assert r.json()["status"] == "mfa_required" and "user" not in r.json()
    assert "set-cookie" not in r.headers
    token = r.json()["mfa_token"]
    bad = await api.post("/api/v1/auth/login/2fa", csrf=False, json={"mfa_token": token, "code": "000000"})
    assert bad.status_code == 401 and bad.json()["code"] == "mfa_invalid_code"
    ok = await api.post(
        "/api/v1/auth/login/2fa", csrf=False, json={"mfa_token": token, "code": TOTP(secret).now()}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "ok" and ok.json()["recovery_codes_remaining"] == 0
    me = (await api.get("/api/v1/auth/me")).json()
    assert me["mfa_verified"] is True
    # token is single use
    again = await api.post("/api/v1/auth/login/2fa", csrf=False, json={"mfa_token": token, "code": "123456"})
    assert again.json()["code"] == "mfa_token_invalid"
    # replay of the same TOTP code in a new challenge is rejected
    r = await api.post(
        "/api/v1/auth/login", csrf=False, json={"email": "erin@example.com", "password": PASSWORD}
    )
    replay = await api.post(
        "/api/v1/auth/login/2fa",
        csrf=False,
        json={"mfa_token": r.json()["mfa_token"], "code": TOTP(secret).now()},
    )
    assert replay.json()["code"] == "mfa_invalid_code"
    # recovery code path
    from app.auth import mfa

    async with ctx.session() as s:
        codes = await mfa.replace_recovery_codes(s, ctx.svc.passwords, u.id)
        await s.commit()
    r = await api.post(
        "/api/v1/auth/login", csrf=False, json={"email": "erin@example.com", "password": PASSWORD}
    )
    rc = await api.post(
        "/api/v1/auth/login/2fa",
        csrf=False,
        json={"mfa_token": r.json()["mfa_token"], "recovery_code": codes[3]},
    )
    assert rc.status_code == 200 and rc.json()["recovery_codes_remaining"] == 9
    r = await api.post(
        "/api/v1/auth/login", csrf=False, json={"email": "erin@example.com", "password": PASSWORD}
    )
    reuse = await api.post(
        "/api/v1/auth/login/2fa",
        csrf=False,
        json={"mfa_token": r.json()["mfa_token"], "recovery_code": codes[3]},
    )
    assert reuse.json()["code"] == "mfa_invalid_code"
    both = await api.post(
        "/api/v1/auth/login/2fa",
        csrf=False,
        json={"mfa_token": r.json()["mfa_token"], "recovery_code": codes[4], "code": "123456"},
    )
    assert both.status_code == 400
    assert (
        await ctx.scalar(
            sa.select(sa.func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "auth.recovery_code_used")
        )
        == 1
    )


async def test_expired_mfa_token(ctx: Ctx) -> None:
    from app.db.models import OneTimeToken

    secret = pyotp.random_base32(32)
    await ctx.create_user("frank@example.com", totp_secret=secret)
    api = ctx.client()
    r = await api.post(
        "/api/v1/auth/login", csrf=False, json={"email": "frank@example.com", "password": PASSWORD}
    )
    await ctx.execute(sa.update(OneTimeToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    r2 = await api.post(
        "/api/v1/auth/login/2fa",
        csrf=False,
        json={"mfa_token": r.json()["mfa_token"], "code": TOTP(secret).now()},
    )
    assert r2.status_code == 401 and r2.json()["code"] == "mfa_token_invalid"


async def test_mfa_enrollment_required_gate(ctx: Ctx) -> None:
    u = await ctx.create_user("gina@example.com")
    await ctx.create_workspace("team-a", {u.id: WorkspaceRole.ADMIN})
    api = ctx.client()
    r = await ctx.login(api, "gina@example.com")
    assert r.json()["mfa_enrollment_required"] is True
    me = await api.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["mfa_enrollment_required"] is True
    blocked = await api.get("/api/v1/workspaces")
    assert blocked.status_code == 403 and blocked.json()["code"] == "mfa_enrollment_required"
    setup = await api.post("/api/v1/auth/2fa/totp/setup", json={"password": PASSWORD})
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert len(secret) == 32 and setup.json()["otpauth_uri"].startswith(
        "otpauth://totp/Hibiscus:gina%40example.com"
    )
    en = await api.post("/api/v1/auth/2fa/totp/enable", json={"code": TOTP(secret).now()})
    assert en.status_code == 200 and len(en.json()["recovery_codes"]) == 10
    ok = await api.get("/api/v1/workspaces")
    assert ok.status_code == 200 and len(ok.json()["items"]) == 1
    me = (await api.get("/api/v1/auth/me")).json()
    assert me["mfa_verified"] is True and me["mfa_enrollment_required"] is False


async def test_refresh_rotation_and_reuse_detection(ctx: Ctx) -> None:
    u = await ctx.create_user("hank@example.com")
    api = ctx.client()
    await ctx.login(api, "hank@example.com")
    old_refresh = api.http.cookies.get("hb_refresh", path="/api/v1/auth")
    assert old_refresh
    # CSRF required
    r = await api.post("/api/v1/auth/refresh", csrf=False)
    assert r.status_code == 403 and r.json()["code"] == "csrf_failed"
    r = await api.post("/api/v1/auth/refresh")
    assert r.status_code == 204, r.text
    new_refresh = api.http.cookies.get("hb_refresh", path="/api/v1/auth")
    assert new_refresh and new_refresh != old_refresh
    assert (await api.get("/api/v1/auth/me")).status_code == 200
    # a concurrent tab presenting the just-rotated token inside the grace window gets a no-op 204
    attacker = ctx.client()
    attacker.http.cookies.set("hb_refresh", old_refresh, domain="testserver.local", path="/api/v1/auth")
    attacker.http.cookies.set("hb_csrf", "c" * 43, domain="testserver.local", path="/")
    r = await attacker.post("/api/v1/auth/refresh")
    assert r.status_code == 204 and "set-cookie" not in r.headers
    # after the grace window, reuse revokes the whole family
    await ctx.execute(
        sa.update(Session)
        .where(Session.user_id == u.id, Session.rotated_at.is_not(None))
        .values(rotated_at=datetime.now(UTC) - timedelta(minutes=5))
    )
    r = await attacker.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.json()["code"] == "refresh_reuse_detected"
    me = await api.get("/api/v1/auth/me")
    assert me.status_code == 401 and me.json()["code"] == "session_revoked"
    r = await api.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.json()["code"] == "session_revoked"
    assert (
        await ctx.scalar(
            sa.select(sa.func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "auth.refresh_reuse")
        )
        == 1
    )


async def test_refresh_errors(ctx: Ctx) -> None:
    u = await ctx.create_user("ivan@example.com")
    api = ctx.client()
    api.http.cookies.set("hb_csrf", "c" * 43, domain="testserver.local", path="/")
    r = await api.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.json()["code"] == "unauthenticated"
    api.http.cookies.set("hb_refresh", "x" * 43, domain="testserver.local", path="/api/v1/auth")
    r = await api.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.json()["code"] == "unauthenticated"
    api2 = ctx.client()
    await ctx.login(api2, "ivan@example.com")
    await ctx.execute(
        sa.update(Session).where(Session.user_id == u.id).values(idle_expires_at=datetime.now(UTC))
    )
    r = await api2.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.json()["code"] == "session_revoked"
    reason = await ctx.scalar(sa.select(Session.revoked_reason).where(Session.user_id == u.id))
    assert reason == "expired"
    api3 = ctx.client()
    await ctx.login(api3, "ivan@example.com")
    await ctx.execute(sa.update(User).where(User.id == u.id).values(is_active=False))
    r = await api3.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.json()["code"] == "session_revoked"


async def test_access_token_expired_and_invalid(ctx: Ctx) -> None:
    u = await ctx.create_user("jill@example.com")
    api = ctx.client()
    await ctx.login(api, "jill@example.com")
    sid = await ctx.scalar(sa.select(Session.family_id).where(Session.user_id == u.id))
    old = ctx.svc.jwt.issue(u.id, sid, False, now=int(datetime.now(UTC).timestamp()) - 3600)
    api.http.cookies.set("hb_access", old, domain="testserver.local", path="/api")
    r = await api.get("/api/v1/auth/me")
    assert r.status_code == 401 and r.json()["code"] == "token_expired"
    api.http.cookies.set("hb_access", "garbage.token.value", domain="testserver.local", path="/api")
    r = await api.get("/api/v1/auth/me")
    assert r.status_code == 401 and r.json()["code"] == "unauthenticated"
    anon = ctx.client()
    r = await anon.get("/api/v1/auth/me")
    assert r.status_code == 401 and r.json()["code"] == "unauthenticated"
    r = await anon.get("/api/v1/auth/me", headers={"Authorization": "Basic abc"})
    assert r.status_code == 401


async def test_logout_revokes_and_clears(ctx: Ctx) -> None:
    u = await ctx.create_user("kate@example.com")
    api = ctx.client()
    await ctx.login(api, "kate@example.com")
    r = await api.post("/api/v1/auth/logout", csrf=False)
    assert r.status_code == 403 and r.json()["code"] == "csrf_failed"
    r = await api.post("/api/v1/auth/logout")
    assert r.status_code == 204
    cleared = r.headers.get_list("set-cookie")
    assert any(
        c.startswith(('hb_access=""', "hb_access=;")) or ("hb_access=" in c and "Max-Age=0" in c)
        for c in cleared
    )
    assert await ctx.scalar(sa.select(Session.revoked_reason).where(Session.user_id == u.id)) == "logout"
    # idempotent without cookies
    anon = ctx.client()
    assert (await anon.post("/api/v1/auth/logout", csrf=False)).status_code == 204


async def test_logout_with_only_refresh_cookie(ctx: Ctx) -> None:
    u = await ctx.create_user("liam@example.com")
    api = ctx.client()
    await ctx.login(api, "liam@example.com")
    api.http.cookies.delete("hb_access", domain="testserver.local", path="/api")
    r = await api.post("/api/v1/auth/logout")
    assert r.status_code == 204
    assert await ctx.scalar(sa.select(Session.revoked_at).where(Session.user_id == u.id)) is not None


async def test_cf_connecting_ip_trust(make_ctx: object) -> None:
    from collections.abc import Awaitable, Callable

    factory: Callable[..., Awaitable[Ctx]] = make_ctx  # type: ignore[assignment]
    ctx = await factory(trusted_proxy_cidrs=["10.0.0.0/8"])
    await ctx.create_user("mia@example.com")
    trusted = ctx.client(client_ip="10.1.2.3")
    await trusted.post(
        "/api/v1/auth/login",
        csrf=False,
        json={"email": "mia@example.com", "password": PASSWORD},
        headers={"CF-Connecting-IP": "203.0.113.7"},
    )
    spoof = ctx.client(client_ip="192.0.2.50")
    await spoof.post(
        "/api/v1/auth/login",
        csrf=False,
        json={"email": "mia@example.com", "password": PASSWORD},
        headers={"CF-Connecting-IP": "203.0.113.8"},
    )
    ips = sorted(str(x) for x in (await _all(ctx, sa.select(Session.ip))))
    assert ips == ["192.0.2.50", "203.0.113.7"]


async def _all(ctx: Ctx, stmt: sa.Select[tuple[object]]) -> list[object]:
    async with ctx.session() as s:
        return list((await s.execute(stmt)).scalars().all())
