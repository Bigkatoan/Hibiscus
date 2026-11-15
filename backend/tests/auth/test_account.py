"""Password reset/change, email verification, 2FA management, sessions, users/me, HF token."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pyotp
import sqlalchemy as sa
from pyotp.totp import TOTP

from app.core.email import NoneEmailSender
from app.db.models import AuditEvent, OneTimeToken, Session, User, UserSecret, WorkspaceRole
from tests.auth.fixtures import PASSWORD, Ctx, token_from

NEW_PASSWORD = "Another-Strong-Pass-42"


async def _count(ctx: Ctx, action: str) -> int:
    return int(
        await ctx.scalar(
            sa.select(sa.func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    )


async def test_forgot_and_reset_password(ctx: Ctx) -> None:
    u = await ctx.create_user("anna@example.com")
    sender = ctx.svc.email
    assert isinstance(sender, NoneEmailSender)
    other = ctx.client()
    await ctx.login(other, "anna@example.com")
    await ctx.execute(sa.update(User).where(User.id == u.id).values(failed_login_count=3))
    api = ctx.client()
    r = await api.post("/api/v1/auth/password/forgot", csrf=False, json={"email": "anna@example.com"})
    assert r.status_code == 202
    r2 = await api.post("/api/v1/auth/password/forgot", csrf=False, json={"email": "ghost@example.com"})
    assert r2.status_code == 202
    assert len(sender.outbox) == 1
    msg = sender.outbox[0]
    assert msg.to == "anna@example.com" and "reset-password#token=" in msg.text
    token = token_from(msg.text)
    weak = await api.post(
        "/api/v1/auth/password/reset", csrf=False, json={"token": token, "new_password": "aaaaaaaaaaaa"}
    )
    assert weak.status_code == 422 and weak.json()["code"] == "password_too_weak"
    breached = await api.post(
        "/api/v1/auth/password/reset", csrf=False, json={"token": token, "new_password": "Password1234!"}
    )
    assert breached.status_code == 422 and breached.json()["code"] == "password_breached"
    short = await api.post(
        "/api/v1/auth/password/reset", csrf=False, json={"token": token, "new_password": "short"}
    )
    assert short.status_code == 422 and short.json()["code"] == "validation_failed"
    ok = await api.post(
        "/api/v1/auth/password/reset", csrf=False, json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert ok.status_code == 204
    again = await api.post(
        "/api/v1/auth/password/reset", csrf=False, json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert again.status_code == 400 and again.json()["code"] == "one_time_token_invalid"
    # all sessions revoked, lockout cleared, new password works, old does not
    assert (await other.get("/api/v1/auth/me")).json()["code"] == "session_revoked"
    assert await ctx.scalar(sa.select(User.failed_login_count).where(User.id == u.id)) == 0
    assert (await ctx.login(ctx.client(), "anna@example.com")).status_code == 401
    assert (await ctx.login(ctx.client(), "anna@example.com", NEW_PASSWORD)).status_code == 200
    assert await _count(ctx, "auth.password_reset_requested") == 1
    assert await _count(ctx, "auth.password_reset") == 1


async def test_forgot_password_rate_limited_silently(ctx: Ctx) -> None:
    await ctx.create_user("ben@example.com")
    api = ctx.client()
    for _ in range(8):
        r = await api.post("/api/v1/auth/password/forgot", csrf=False, json={"email": "ben@example.com"})
        assert r.status_code == 202
    sender = ctx.svc.email
    assert isinstance(sender, NoneEmailSender)
    assert len(sender.outbox) == ctx.settings.rl_forgot_per_hour


async def test_reset_token_expired(ctx: Ctx) -> None:
    await ctx.create_user("cara@example.com")
    api = ctx.client()
    await api.post("/api/v1/auth/password/forgot", csrf=False, json={"email": "cara@example.com"})
    sender = ctx.svc.email
    assert isinstance(sender, NoneEmailSender)
    token = token_from(sender.outbox[-1].text)
    await ctx.execute(sa.update(OneTimeToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    r = await api.post(
        "/api/v1/auth/password/reset", csrf=False, json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert r.status_code == 400 and r.json()["code"] == "one_time_token_invalid"


async def test_change_password(ctx: Ctx) -> None:
    u = await ctx.create_user("dina@example.com", display_name="Dina")
    a, b = ctx.client(), ctx.client()
    await ctx.login(a, "dina@example.com")
    await ctx.login(b, "dina@example.com")
    r = await a.post(
        "/api/v1/auth/password/change", json={"current_password": "wrong", "new_password": NEW_PASSWORD}
    )
    assert r.status_code == 401 and r.json()["code"] == "password_incorrect"
    r = await a.post(
        "/api/v1/auth/password/change", json={"current_password": PASSWORD, "new_password": "dina-dina-1234"}
    )
    assert r.status_code == 422 and r.json()["code"] == "password_too_weak"
    r = await a.post(
        "/api/v1/auth/password/change", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    )
    assert r.status_code == 204
    assert (await a.get("/api/v1/auth/me")).status_code == 200
    assert (await b.get("/api/v1/auth/me")).json()["code"] == "session_revoked"
    assert (
        await ctx.scalar(
            sa.select(sa.func.count())
            .select_from(Session)
            .where(Session.user_id == u.id, Session.revoked_at.is_(None))
        )
        == 1
    )


async def test_email_verify_and_resend(ctx: Ctx) -> None:
    u = await ctx.create_user("eve@example.com")
    await ctx.execute(sa.update(User).where(User.id == u.id).values(email_verified_at=None))
    api = ctx.client()
    await ctx.login(api, "eve@example.com")
    assert (await api.get("/api/v1/auth/me")).json()["user"]["email_verified"] is False
    r = await api.post("/api/v1/auth/email/resend")
    assert r.status_code == 202
    sender = ctx.svc.email
    assert isinstance(sender, NoneEmailSender)
    token = token_from(sender.outbox[-1].text)
    bad = await api.post("/api/v1/auth/email/verify", csrf=False, json={"token": "x" * 40})
    assert bad.status_code == 400 and bad.json()["code"] == "one_time_token_invalid"
    ok = await api.post("/api/v1/auth/email/verify", csrf=False, json={"token": token})
    assert ok.status_code == 204
    assert (await api.get("/api/v1/auth/me")).json()["user"]["email_verified"] is True
    n = len(sender.outbox)
    assert (await api.post("/api/v1/auth/email/resend")).status_code == 202
    assert len(sender.outbox) == n  # already verified => nothing sent


async def test_totp_lifecycle(ctx: Ctx) -> None:
    u = await ctx.create_user("finn@example.com")
    api = ctx.client()
    await ctx.login(api, "finn@example.com")
    r = await api.post("/api/v1/auth/2fa/totp/enable", json={"code": "123456"})
    assert r.status_code == 409 and r.json()["code"] == "conflict"
    r = await api.post("/api/v1/auth/2fa/totp/setup", json={"password": "wrong"})
    assert r.status_code == 401 and r.json()["code"] == "password_incorrect"
    secret = (await api.post("/api/v1/auth/2fa/totp/setup", json={"password": PASSWORD})).json()["secret"]
    totp = TOTP(secret)
    r = await api.post("/api/v1/auth/2fa/totp/enable", json={"code": "000000"})
    assert r.status_code == 401 and r.json()["code"] == "mfa_invalid_code"
    r = await api.post("/api/v1/auth/2fa/totp/enable", json={"code": totp.now()})
    assert r.status_code == 200
    codes = r.json()["recovery_codes"]
    assert len(set(codes)) == 10
    assert (await api.post("/api/v1/auth/2fa/totp/setup", json={"password": PASSWORD})).json()[
        "code"
    ] == "mfa_already_enabled"
    assert (await api.post("/api/v1/auth/2fa/totp/enable", json={"code": totp.now()})).json()[
        "code"
    ] == "mfa_already_enabled"
    # stored secret is encrypted, not plaintext
    enc = await ctx.scalar(sa.select(User.totp_secret_enc).where(User.id == u.id))
    assert secret.encode() not in enc
    # regenerate recovery codes
    await ctx.reset_totp_step(u.id)
    r = await api.post("/api/v1/auth/2fa/recovery-codes", json={"code": "000000"})
    assert r.status_code == 401
    r = await api.post("/api/v1/auth/2fa/recovery-codes", json={"code": totp.now()})
    assert r.status_code == 200 and set(r.json()["recovery_codes"]).isdisjoint(codes)
    # every wrong password / code above counted towards the lockout (SEC-auth-02): 3 so far
    assert await ctx.scalar(sa.select(User.failed_login_count).where(User.id == u.id)) == 3
    await ctx.execute(sa.update(User).where(User.id == u.id).values(failed_login_count=0))
    await ctx.svc.redis.flushdb()  # and towards the per-user re-auth rate limit (10 / 15 min)
    # disable
    await ctx.reset_totp_step(u.id)
    r = await api.post("/api/v1/auth/2fa/totp/disable", json={"password": "bad", "code": totp.now()})
    assert r.json()["code"] == "password_incorrect"
    r = await api.post("/api/v1/auth/2fa/totp/disable", json={"password": PASSWORD, "code": "000000"})
    assert r.json()["code"] == "mfa_invalid_code"
    r = await api.post("/api/v1/auth/2fa/totp/disable", json={"password": PASSWORD, "code": totp.now()})
    assert r.status_code == 204
    assert (
        await api.post("/api/v1/auth/2fa/totp/disable", json={"password": PASSWORD, "code": totp.now()})
    ).status_code == 409
    assert (await api.post("/api/v1/auth/2fa/recovery-codes", json={"code": totp.now()})).status_code == 409
    for action in ("auth.mfa_enabled", "auth.mfa_disabled", "auth.recovery_codes_regenerated"):
        assert await _count(ctx, action) == 1


async def test_totp_disable_refused_for_admin_roles(ctx: Ctx) -> None:
    secret = pyotp.random_base32(32)
    u = await ctx.create_user("gus@example.com", totp_secret=secret)
    await ctx.create_workspace("ops", {u.id: WorkspaceRole.OWNER})
    api = ctx.client()
    await ctx.login(api, "gus@example.com", totp_secret=secret)
    await ctx.reset_totp_step(u.id)
    r = await api.post(
        "/api/v1/auth/2fa/totp/disable", json={"password": PASSWORD, "code": TOTP(secret).now()}
    )
    assert r.status_code == 409 and r.json()["code"] == "mfa_required_by_role"


async def test_sessions_list_and_revoke(ctx: Ctx) -> None:
    await ctx.create_user("hugo@example.com")
    a, b, c = ctx.client(), ctx.client(), ctx.client()
    for x in (a, b, c):
        await ctx.login(x, "hugo@example.com")
    await a.post("/api/v1/auth/refresh")  # rotation keeps one entry per family
    r = await a.get("/api/v1/auth/sessions")
    items = r.json()["items"]
    assert len(items) == 3 and sum(i["current"] for i in items) == 1
    mine = next(i for i in items if i["current"])
    other_id = next(i["id"] for i in items if not i["current"])
    assert (await a.delete("/api/v1/auth/sessions/00000000-0000-4000-8000-000000000000")).status_code == 404
    assert (await a.delete(f"/api/v1/auth/sessions/{other_id}")).status_code == 204
    assert len((await a.get("/api/v1/auth/sessions")).json()["items"]) == 2
    assert (await a.post("/api/v1/auth/sessions/revoke-others")).status_code == 204
    items = (await a.get("/api/v1/auth/sessions")).json()["items"]
    assert [i["id"] for i in items] == [mine["id"]]
    assert (await b.get("/api/v1/auth/me")).status_code == 401
    assert (await c.get("/api/v1/auth/me")).status_code == 401


async def test_other_users_session_is_404(ctx: Ctx) -> None:
    await ctx.create_user("ida@example.com")
    await ctx.create_user("joe@example.com")
    a, b = ctx.client(), ctx.client()
    await ctx.login(a, "ida@example.com")
    await ctx.login(b, "joe@example.com")
    sid = (await b.get("/api/v1/auth/me")).json()["session_id"]
    assert (await a.delete(f"/api/v1/auth/sessions/{sid}")).status_code == 404
    assert (await b.get("/api/v1/auth/me")).status_code == 200


async def test_update_me_and_hf_token(ctx: Ctx) -> None:
    u = await ctx.create_user("kim@example.com")
    api = ctx.client()
    await ctx.login(api, "kim@example.com")
    r = await api.patch("/api/v1/users/me", json={})
    assert r.status_code == 422
    r = await api.patch("/api/v1/users/me", json={"locale": "fr"})
    assert r.status_code == 422
    r = await api.patch("/api/v1/users/me", json={"display_name": "Kim L", "locale": "en"})
    assert r.status_code == 200 and r.json()["display_name"] == "Kim L" and r.json()["locale"] == "en"
    r = await api.patch("/api/v1/users/me", json={"display_name": None})
    assert r.status_code == 422
    assert (await api.get("/api/v1/users/me/secrets/hf-token")).json() == {
        "present": False,
        "hint": None,
        "updated_at": None,
    }
    r = await api.put("/api/v1/users/me/secrets/hf-token", json={"token": "hf_abcdefghijklmnopQRST"})
    assert r.status_code == 200 and r.json()["present"] is True and r.json()["hint"] == "…QRST"
    blob = await ctx.scalar(sa.select(UserSecret.ciphertext).where(UserSecret.user_id == u.id))
    assert b"hf_abcdefghijklmnop" not in blob
    r = await api.put("/api/v1/users/me/secrets/hf-token", json={"token": "hf_zzzzzzzzzzzz9999"})
    assert r.json()["hint"] == "…9999"
    from app.auth.users_router import read_hf_token

    class _Req:
        app = ctx.app

    async with ctx.session() as s:
        assert await read_hf_token(s, _Req(), u.id) == "hf_zzzzzzzzzzzz9999"  # type: ignore[arg-type]
    assert (await api.delete("/api/v1/users/me/secrets/hf-token")).status_code == 204
    assert (await api.get("/api/v1/users/me/secrets/hf-token")).json()["present"] is False
    async with ctx.session() as s:
        assert await read_hf_token(s, _Req(), str(u.id)) is None  # type: ignore[arg-type]
    assert await _count(ctx, "secret.updated") == 3
    assert await _count(ctx, "user.updated") == 1


async def test_csrf_required_on_unsafe_cookie_requests(ctx: Ctx) -> None:
    await ctx.create_user("lea@example.com")
    api = ctx.client()
    await ctx.login(api, "lea@example.com")
    r = await api.http.patch("/api/v1/users/me", json={"locale": "en"})
    assert r.status_code == 403 and r.json()["code"] == "csrf_failed"
    r = await api.http.patch("/api/v1/users/me", json={"locale": "en"}, headers={"X-CSRF-Token": "x" * 43})
    assert r.status_code == 403 and r.json()["code"] == "csrf_failed"
    # /auth/me re-issues a missing csrf cookie
    api.http.cookies.delete("hb_csrf")
    r = await api.get("/api/v1/auth/me")
    assert any(c.startswith("hb_csrf=") for c in r.headers.get_list("set-cookie"))
