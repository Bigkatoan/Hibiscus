"""Phase-5 auth hardening regressions (docs/qa/phase4-findings.md, CONTRACT_NOTES CR-BE-S1).

SEC-auth-01 (2FA enrolment vs other sessions, MFA roles need a 2FA-verified session),
SEC-auth-02 (re-auth rate limit + lockout), SEC-auth-03 (SSE re-authorization),
SEC-auth-04 (invite token out of URL paths / logs), SEC-auth-06 (no lockout oracle),
QC-e2e-07 (refresh after an aborted rotation), QC-e2e-02 (shared dev keys).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyotp
import pytest
import sqlalchemy as sa
from pyotp.totp import TOTP

from app.core.crypto import sha256
from app.core.deps import Principal, StreamAuthGuard
from app.core.middleware import redact_path
from app.core.settings import Settings
from app.db.models import AuditEvent, Invite, Membership, Session, User, WorkspaceRole
from tests.auth.fixtures import PASSWORD, Ctx

BACKEND = Path(__file__).resolve().parents[2]


async def _audit(ctx: Ctx, action: str) -> list[AuditEvent]:
    async with ctx.session() as s:
        rows = await s.execute(sa.select(AuditEvent).where(AuditEvent.action == action))
        return list(rows.scalars())


# ---------------------------------------------------------------------------------------------
# SEC-auth-01
# ---------------------------------------------------------------------------------------------
async def test_enable_totp_revokes_every_other_session(ctx: Ctx) -> None:
    u = await ctx.create_user("alice@example.com")
    await ctx.create_workspace("lab", {u.id: WorkspaceRole.MEMBER})
    stolen, device_b = ctx.client(), ctx.client()
    await ctx.login(stolen, u.email)
    await ctx.login(device_b, u.email)
    secret = (await device_b.post("/api/v1/auth/2fa/totp/setup", json={"password": PASSWORD})).json()[
        "secret"
    ]
    r = await device_b.post("/api/v1/auth/2fa/totp/enable", json={"code": TOTP(secret).now()})
    assert r.status_code == 200, r.text
    # the session that never passed 2FA is gone, refresh included
    r = await stolen.get("/api/v1/auth/me")
    assert r.status_code == 401 and r.json()["code"] == "session_revoked"
    r = await stolen.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.json()["code"] == "session_revoked"
    me = (await device_b.get("/api/v1/auth/me")).json()
    assert me["mfa_verified"] is True
    (ev,) = await _audit(ctx, "auth.mfa_enabled")
    assert ev.details["other_sessions_revoked"] == 1


async def test_mfa_role_session_that_never_passed_2fa_is_refused(ctx: Ctx) -> None:
    secret = pyotp.random_base32(32)
    owner = await ctx.create_user("bob@example.com", totp_secret=secret)
    member = await ctx.create_user("mia@example.com", totp_secret=secret)
    ws = await ctx.create_workspace("ops", {owner.id: WorkspaceRole.OWNER, member.id: WorkspaceRole.MEMBER})
    api, mapi = ctx.client(), ctx.client()
    await ctx.login(api, owner.email, totp_secret=secret)
    await ctx.login(mapi, member.email, totp_secret=secret)
    assert (await api.get(f"/api/v1/workspaces/{ws.id}")).status_code == 200
    # e.g. a session opened before 2FA was enabled (mfa_verified is copied across refreshes)
    await ctx.execute(sa.update(Session).values(mfa_verified=False))
    r = await api.patch(f"/api/v1/workspaces/{ws.id}", json={"name": "Taken Over"})
    assert r.status_code == 403 and r.json()["code"] == "mfa_reauth_required"
    r = await api.post(
        f"/api/v1/workspaces/{ws.id}/invites", json={"email": "x@example.com", "role": "admin"}
    )
    assert r.status_code == 403 and r.json()["code"] == "mfa_reauth_required"
    assert (await api.get(f"/api/v1/workspaces/{ws.id}")).status_code == 403
    # what the SPA needs to show the state and log in again still works
    me = await api.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["mfa_verified"] is False
    assert (await api.post("/api/v1/auth/logout")).status_code == 204
    # roles without the 2FA requirement are unaffected
    assert (await mapi.get(f"/api/v1/workspaces/{ws.id}")).status_code == 200


# ---------------------------------------------------------------------------------------------
# SEC-auth-02
# ---------------------------------------------------------------------------------------------
async def test_wrong_passwords_from_a_session_lock_the_account(ctx: Ctx) -> None:
    u = await ctx.create_user("carl@example.com")
    api = ctx.client()
    await ctx.login(api, u.email)
    for _ in range(5):
        r = await api.post("/api/v1/auth/2fa/totp/setup", json={"password": "guess-guess-guess"})
        assert r.status_code == 401 and r.json()["code"] == "password_incorrect"
    # locked: even the right password is refused, here and at /auth/login
    r = await api.post("/api/v1/auth/2fa/totp/setup", json={"password": PASSWORD})
    assert r.status_code == 423 and r.json()["code"] == "account_locked"
    r = await api.post(
        "/api/v1/auth/password/change",
        json={"current_password": PASSWORD, "new_password": "Another-Good-Passphrase-7"},
    )
    assert r.status_code == 423
    r = await ctx.client().post(
        "/api/v1/auth/login", csrf=False, json={"email": u.email, "password": PASSWORD}
    )
    assert r.status_code == 401
    assert await ctx.scalar(sa.select(User.failed_login_count).where(User.id == u.id)) == 5
    failed = await _audit(ctx, "auth.login_failed")
    assert sum(1 for e in failed if e.details.get("reason") == "reauth_bad_password") == 5
    assert len(await _audit(ctx, "auth.account_locked")) == 1


async def test_wrong_totp_codes_from_a_session_lock_the_account(ctx: Ctx) -> None:
    u = await ctx.create_user("cora@example.com")
    api = ctx.client()
    await ctx.login(api, u.email)
    secret = (await api.post("/api/v1/auth/2fa/totp/setup", json={"password": PASSWORD})).json()["secret"]
    good = TOTP(secret).now()
    bad = f"{(int(good) + 1) % 1_000_000:06d}"
    for _ in range(5):
        r = await api.post("/api/v1/auth/2fa/totp/enable", json={"code": bad})
        assert r.status_code == 401 and r.json()["code"] == "mfa_invalid_code"
    r = await api.post("/api/v1/auth/2fa/totp/enable", json={"code": good})
    assert r.status_code == 423
    failed = await _audit(ctx, "auth.login_failed")
    assert sum(1 for e in failed if e.details.get("reason") == "bad_second_factor") == 5


async def test_reauth_checks_are_rate_limited_per_user(make_ctx: Any) -> None:
    ctx: Ctx = await make_ctx(rl_reauth_per_15min=3)
    u = await ctx.create_user("cleo@example.com")
    api = ctx.client()
    await ctx.login(api, u.email)
    body = {"current_password": "guess-guess-guess", "new_password": "Another-Good-Passphrase-7"}
    for _ in range(3):
        assert (await api.post("/api/v1/auth/password/change", json=body)).status_code == 401
    r = await api.post("/api/v1/auth/password/change", json=body)
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"


# ---------------------------------------------------------------------------------------------
# SEC-auth-06
# ---------------------------------------------------------------------------------------------
async def test_lockout_does_not_reveal_whether_an_account_exists(ctx: Ctx) -> None:
    await ctx.create_user("dora@example.com")

    async def attempts(email: str, ip: str) -> list[tuple[int, str, bool]]:
        api = ctx.client(client_ip=ip)
        out = []
        for _ in range(7):
            r = await api.post(
                "/api/v1/auth/login", csrf=False, json={"email": email, "password": "nope-nope"}
            )
            out.append((r.status_code, r.json()["code"], "retry-after" in r.headers))
        return out

    existing = await attempts("dora@example.com", "127.0.0.2")
    unknown = await attempts("nobody@example.com", "127.0.0.3")
    assert existing == unknown == [(401, "invalid_credentials", False)] * 7


# ---------------------------------------------------------------------------------------------
# SEC-auth-04
# ---------------------------------------------------------------------------------------------
class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


async def test_invite_token_travels_in_the_body_and_never_reaches_the_access_log(ctx: Ctx) -> None:
    secret = pyotp.random_base32(32)
    owner = await ctx.create_user("olga@example.com", totp_secret=secret)
    eve = await ctx.create_user("eve@example.com")
    ws = await ctx.create_workspace("lab", {owner.id: WorkspaceRole.OWNER})
    token = "Tk_" + "a1B2" * 10
    async with ctx.session() as s:
        s.add(
            Invite(
                workspace_id=ws.id,
                email=eve.email,
                role=WorkspaceRole.MEMBER,
                token_hash=sha256(token),
                invited_by=owner.id,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await s.commit()
    access = logging.getLogger("hibiscus.access")
    handler, level = _Records(), access.level
    access.addHandler(handler)
    access.setLevel(logging.INFO)
    try:
        anon = ctx.client()
        r = await anon.post("/api/v1/auth/invites/preview", csrf=False, json={"token": token})
        assert r.status_code == 200 and r.json()["email"] == eve.email
        r = await anon.post("/api/v1/auth/invites/preview", csrf=False, json={"token": "z" * 43})
        assert r.status_code == 404 and r.json()["code"] == "invite_invalid"
        # deprecated path variant still answers, but its path is redacted in the access log
        assert (await anon.get(f"/api/v1/auth/invites/{token}")).status_code == 200
        eapi = ctx.client()
        await ctx.login(eapi, eve.email)
        r = await eapi.post("/api/v1/auth/invites/accept", json={"token": token})
        assert r.status_code == 200 and r.json()["workspace_id"] == str(ws.id)
    finally:
        access.removeHandler(handler)
        access.setLevel(level)
    paths = [str(getattr(rec, "path", "")) for rec in handler.records]
    assert "/api/v1/auth/invites/REDACTED" in paths and "/api/v1/auth/invites/preview" in paths
    assert not any(token in p for p in paths)
    assert await ctx.scalar(
        sa.select(Membership.role).where(Membership.workspace_id == ws.id, Membership.user_id == eve.id)
    )


def test_redact_path() -> None:
    tok = "x" * 43
    assert redact_path(f"/api/v1/auth/invites/{tok}") == "/api/v1/auth/invites/REDACTED"
    assert redact_path(f"/api/v1/auth/invites/{tok}/accept") == "/api/v1/auth/invites/REDACTED/accept"
    assert redact_path("/api/v1/auth/invites/preview") == "/api/v1/auth/invites/preview"
    assert redact_path("/api/v1/auth/invites/accept") == "/api/v1/auth/invites/accept"
    assert redact_path("/api/v1/runs") == "/api/v1/runs"


# ---------------------------------------------------------------------------------------------
# QC-e2e-07
# ---------------------------------------------------------------------------------------------
async def _age_sessions(ctx: Ctx, user_id: uuid.UUID, *, rotated_only: bool = False) -> None:
    """Move the family 5 minutes into the past (well beyond the 10 s grace window)."""
    five = timedelta(minutes=5)
    values: dict[str, Any] = {"rotated_at": Session.rotated_at - five}
    if not rotated_only:
        values["last_used_at"] = Session.last_used_at - five
    await ctx.execute(sa.update(Session).where(Session.user_id == user_id).values(**values))


async def test_refresh_whose_response_was_lost_does_not_revoke_the_session(ctx: Ctx) -> None:
    u = await ctx.create_user("hugo@example.com")
    api = ctx.client()
    await ctx.login(api, u.email)
    old_refresh = api.http.cookies.get("hb_refresh", path="/api/v1/auth")
    csrf = api.http.cookies.get("hb_csrf")
    assert old_refresh and csrf
    # A page reload aborts the refresh after the server rotated the token: the browser never
    # stores the response cookies (simulated by sending it from a copy of the cookie jar).
    lost = ctx.client()
    lost.http.cookies.set("hb_refresh", old_refresh, domain="testserver.local", path="/api/v1/auth")
    lost.http.cookies.set("hb_csrf", csrf, domain="testserver.local", path="/")
    assert (await lost.post("/api/v1/auth/refresh")).status_code == 204
    # the browser keeps using its old, still valid access token: that does not confirm the successor
    assert (await api.get("/api/v1/auth/me")).status_code == 200
    await _age_sessions(ctx, u.id)
    r = await api.post("/api/v1/auth/refresh")
    assert r.status_code == 204, r.text
    assert api.http.cookies.get("hb_refresh", path="/api/v1/auth") not in (None, old_refresh)
    assert (await api.get("/api/v1/auth/me")).status_code == 200  # confirms the new successor
    assert not await _audit(ctx, "auth.refresh_reuse")
    assert await ctx.scalar(sa.select(sa.func.count()).where(Session.revoked_at.is_not(None))) == 0
    # once the successor has been used, the old token is genuine reuse again
    await _age_sessions(ctx, u.id, rotated_only=True)
    r = await lost.post("/api/v1/auth/refresh")  # `lost` now holds the (unused, superseded) successor
    assert r.status_code == 401 and r.json()["code"] == "refresh_reuse_detected"
    assert (await api.get("/api/v1/auth/me")).status_code == 401


async def test_repeatedly_aborted_refreshes_keep_the_session(ctx: Ctx) -> None:
    u = await ctx.create_user("ines@example.com")
    api = ctx.client()
    await ctx.login(api, u.email)
    old_refresh = api.http.cookies.get("hb_refresh", path="/api/v1/auth")
    assert old_refresh
    for _ in range(3):
        lost = ctx.client()
        lost.http.cookies.set("hb_refresh", old_refresh, domain="testserver.local", path="/api/v1/auth")
        lost.http.cookies.set("hb_csrf", "c" * 43, domain="testserver.local", path="/")
        assert (await lost.post("/api/v1/auth/refresh")).status_code == 204
        await _age_sessions(ctx, u.id)
    assert (await api.post("/api/v1/auth/refresh")).status_code == 204
    assert (await api.get("/api/v1/auth/me")).status_code == 200


# ---------------------------------------------------------------------------------------------
# SEC-auth-03
# ---------------------------------------------------------------------------------------------
async def _session_principal(ctx: Ctx, user: User, ws_id: uuid.UUID) -> Principal:
    fam = await ctx.scalar(sa.select(Session.family_id).where(Session.user_id == user.id).limit(1))
    return Principal(
        user_id=user.id,
        workspace_ids_roles={ws_id: WorkspaceRole.MEMBER},
        auth_method="session",
        token_scopes=frozenset(),
        token_workspace_id=None,
        mfa_verified=False,
        session_id=fam,
    )


async def test_stream_guard_rechecks_session_membership_and_lifetime(ctx: Ctx) -> None:
    u = await ctx.create_user("sam@example.com")
    ws = await ctx.create_workspace("lab", {u.id: WorkspaceRole.MEMBER})
    api = ctx.client()
    await ctx.login(api, u.email)
    p = await _session_principal(ctx, u, ws.id)
    maker = ctx.svc.db.sessionmaker

    def guard(**kw: float) -> StreamAuthGuard:
        return StreamAuthGuard(
            p, ws.id, maker, recheck_s=kw.get("recheck_s", 0), max_lifetime_s=kw.get("life", 60)
        )

    g = guard()
    assert await g.ok()
    assert (await api.post("/api/v1/auth/refresh")).status_code == 204  # rotation keeps it valid
    assert await g.ok()
    assert not await guard(life=0).ok()  # lifetime cap
    # membership removed => closed for good, even if re-added later
    await ctx.execute(sa.delete(Membership).where(Membership.user_id == u.id))
    assert not await g.ok()
    await ctx.execute(
        sa.insert(Membership).values(workspace_id=ws.id, user_id=u.id, role=WorkspaceRole.MEMBER)
    )
    assert not await g.ok()
    g2 = guard()
    assert await g2.ok()
    lazy = guard(recheck_s=3600)  # between re-checks nothing is queried
    assert (await api.post("/api/v1/auth/logout")).status_code == 204
    assert not await g2.ok()
    assert await lazy.ok()
    # PAT: revoking the token ends the stream
    api2 = ctx.client()
    await ctx.login(api2, u.email)
    tok = (
        await api2.post(
            "/api/v1/auth/tokens", json={"name": "s", "workspace_id": str(ws.id), "scopes": ["runs:read"]}
        )
    ).json()
    pat = Principal(
        user_id=u.id,
        workspace_ids_roles={ws.id: WorkspaceRole.MEMBER},
        auth_method="pat",
        token_scopes=frozenset({"runs:read"}),
        token_workspace_id=ws.id,
        mfa_verified=False,
        token_id=uuid.UUID(tok["id"]),
    )
    g3 = StreamAuthGuard(pat, ws.id, maker, recheck_s=0, max_lifetime_s=60)
    assert await g3.ok()
    assert (await api2.delete(f"/api/v1/auth/tokens/{tok['id']}")).status_code == 204
    assert not await g3.ok()


async def test_workspace_stream_closes_when_the_session_is_revoked(make_ctx: Any) -> None:
    """Real uvicorn (ASGITransport buffers streaming bodies)."""
    import socket

    import httpx
    import uvicorn

    ctx: Ctx = await make_ctx(sse_auth_recheck_s=0.2)
    u = await ctx.create_user("vic@example.com")
    ws = await ctx.create_workspace("lab", {u.id: WorkspaceRole.VIEWER})
    api = ctx.client()
    await ctx.login(api, u.email)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(ctx.app, log_level="warning", lifespan="off"))
    serve = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        while not server.started:  # noqa: ASYNC110 - uvicorn exposes a flag, not an event
            await asyncio.sleep(0.05)
        jar = httpx.Cookies()
        for c in api.http.cookies.jar:
            jar.set(c.name, c.value or "")
        opened = asyncio.Event()

        async def consume() -> None:
            async with (
                httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", cookies=jar, timeout=15) as client,
                client.stream("GET", f"/api/v1/workspaces/{ws.id}/events") as resp,
            ):
                assert resp.status_code == 200
                opened.set()
                async for _ in resp.aiter_bytes():
                    pass  # returns when the server closes the stream

        task = asyncio.create_task(consume())
        await asyncio.wait_for(opened.wait(), timeout=10)
        await asyncio.sleep(0.5)
        assert not task.done()  # a valid session keeps the stream open
        await ctx.execute(
            sa.update(Session).where(Session.user_id == u.id).values(revoked_at=datetime.now(UTC))
        )
        await asyncio.wait_for(task, timeout=5)
    finally:
        server.should_exit = True
        await asyncio.wait_for(serve, timeout=10)


# ---------------------------------------------------------------------------------------------
# QC-e2e-02
# ---------------------------------------------------------------------------------------------
_PRINT_KEYS = (
    "import json; from app.core.settings import Settings; s = Settings(); "
    "print(json.dumps([s.jwt_private_key, s.data_key, s.cursor_secret]))"
)


def _keys_in_subprocess(env: dict[str, str]) -> list[str]:
    clean = {k: v for k, v in os.environ.items() if not k.startswith("HIBISCUS_")}
    clean.pop("PYTHONPATH", None)
    out = subprocess.run(  # noqa: S603 - fixed interpreter and arguments
        [sys.executable, "-c", _PRINT_KEYS],
        env={**clean, **env},
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    keys: list[str] = json.loads(out.stdout.strip().splitlines()[-1])
    return keys


def test_dev_keys_are_shared_between_processes(tmp_path: Path) -> None:
    env = {"HIBISCUS_ENV": "dev", "HIBISCUS_DEV_KEYS_FILE": str(tmp_path / "keys.json")}
    first, second = _keys_in_subprocess(env), _keys_in_subprocess(env)
    assert first == second and all(first)
    assert (tmp_path / "keys.json").stat().st_mode & 0o077 == 0
    # with a dev secret the keys are derived (no file), identical everywhere and secret-specific
    seeded = {
        "HIBISCUS_ENV": "dev",
        "HIBISCUS_DEV_SECRET": "s3cret",
        "HIBISCUS_DEV_KEYS_FILE": "/nonexistent/x",
    }
    a, b = _keys_in_subprocess(seeded), _keys_in_subprocess(seeded)
    assert a == b and a != first
    assert _keys_in_subprocess({**seeded, "HIBISCUS_DEV_SECRET": "other"}) != a


def test_dev_keys_race_between_workers(tmp_path: Path) -> None:
    path = tmp_path / "keys.json"
    env = {**os.environ, "HIBISCUS_ENV": "dev", "HIBISCUS_DEV_KEYS_FILE": str(path)}
    env.pop("PYTHONPATH", None)
    procs = [
        subprocess.Popen(  # noqa: S603 - fixed interpreter and arguments
            [sys.executable, "-c", _PRINT_KEYS], env=env, cwd=BACKEND, stdout=subprocess.PIPE, text=True
        )
        for _ in range(6)
    ]
    outs = {p.communicate(timeout=60)[0].strip().splitlines()[-1] for p in procs}
    assert len(outs) == 1
    assert not [f for f in tmp_path.iterdir() if f.name != "keys.json"]  # temp files cleaned up


def test_explicit_keys_win_and_prod_still_requires_them(tmp_path: Path) -> None:
    s = Settings(env="test", cursor_secret="explicit", dev_keys_file=str(tmp_path / "k.json"))
    assert s.cursor_secret == "explicit" and s.jwt_private_key.startswith("-----BEGIN PRIVATE KEY-----")
    with pytest.raises(ValueError, match="missing required secrets in prod"):
        Settings(env="prod", dev_secret="ignored-in-prod")
