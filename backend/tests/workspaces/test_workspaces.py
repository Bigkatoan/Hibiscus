"""Workspaces, members (role matrix), invites (register / accept), usage, workspace SSE."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pyotp
import pytest
import sqlalchemy as sa

from app.db.models import (
    ApiToken,
    AuditEvent,
    Dataset,
    DatasetSource,
    DatasetVersion,
    Invite,
    Membership,
    Quota,
    Run,
    RunEvent,
    RunStatus,
    User,
    WorkspaceRole,
)
from tests.auth.fixtures import Ctx, token_from

SECRET = pyotp.random_base32(32)


async def _admin(ctx: Ctx, email: str = "root@example.com") -> tuple[User, Any]:
    u = await ctx.create_user(email, platform_admin=True, totp_secret=SECRET)
    api = ctx.client()
    r = await ctx.login(api, email, totp_secret=SECRET)
    assert r.status_code == 200, r.text
    return u, api


async def _team(ctx: Ctx) -> dict[str, Any]:
    """owner (2FA), admin (2FA), member, viewer in workspace 'team'."""
    owner = await ctx.create_user("owner@example.com", totp_secret=SECRET)
    admin = await ctx.create_user("admin@example.com", totp_secret=SECRET)
    member = await ctx.create_user("member@example.com")
    viewer = await ctx.create_user("viewer@example.com")
    ws = await ctx.create_workspace(
        "team",
        {
            owner.id: WorkspaceRole.OWNER,
            admin.id: WorkspaceRole.ADMIN,
            member.id: WorkspaceRole.MEMBER,
            viewer.id: WorkspaceRole.VIEWER,
        },
    )
    apis = {}
    for name, u in (("owner", owner), ("admin", admin), ("member", member), ("viewer", viewer)):
        api = ctx.client()
        await ctx.login(api, u.email, totp_secret=SECRET if name in ("owner", "admin") else None)
        apis[name] = api
    return {
        "ws": ws,
        "users": {"owner": owner, "admin": admin, "member": member, "viewer": viewer},
        "api": apis,
    }


async def test_create_workspace_admin_only(ctx: Ctx) -> None:
    _root, api = await _admin(ctx)
    plain = await ctx.create_user("plain@example.com")
    papi = ctx.client()
    await ctx.login(papi, plain.email)
    r = await papi.post("/api/v1/workspaces", json={"name": "Lab", "slug": "lab"})
    assert r.status_code == 403
    r = await api.post("/api/v1/workspaces", json={"name": "Lab", "slug": "lab"})
    assert r.status_code == 201, r.text
    ws = r.json()
    assert ws["my_role"] == "owner" and ws["member_count"] == 1 and ws["settings"]["default_gpu"] == "auto"
    r = await api.post("/api/v1/workspaces", json={"name": "Lab 2", "slug": "lab"})
    assert r.status_code == 409 and r.json()["code"] == "workspace_slug_taken"
    r = await api.post("/api/v1/workspaces", json={"name": "Bad", "slug": "-x"})
    assert r.status_code == 422
    q = await ctx.scalar(
        sa.select(sa.func.count()).select_from(Quota).where(Quota.workspace_id == uuid.UUID(ws["id"]))
    )
    assert q == 1
    listed = (await api.get("/api/v1/workspaces")).json()["items"]
    assert [w["slug"] for w in listed] == ["lab"]
    assert (await papi.get("/api/v1/workspaces")).json() == {"items": []}


async def test_get_update_delete_workspace(ctx: Ctx) -> None:
    t = await _team(ctx)
    ws = t["ws"]
    a = t["api"]
    for role in ("owner", "admin", "member", "viewer"):
        r = await a[role].get(f"/api/v1/workspaces/{ws.id}")
        assert r.status_code == 200 and r.json()["my_role"] == role and r.json()["member_count"] == 4
    outsider = await ctx.create_user("out@example.com")
    oapi = ctx.client()
    await ctx.login(oapi, outsider.email)
    assert (await oapi.get(f"/api/v1/workspaces/{ws.id}")).status_code == 404
    assert (await a["owner"].get(f"/api/v1/workspaces/{uuid.uuid4()}")).status_code == 404
    body = {
        "name": "Team Renamed",
        "settings": {"default_heldout_fraction": 0.2, "notify_on": ["run.failed"]},
    }
    assert (await a["member"].patch(f"/api/v1/workspaces/{ws.id}", json=body)).status_code == 403
    r = await a["admin"].patch(f"/api/v1/workspaces/{ws.id}", json=body)
    assert r.status_code == 200 and r.json()["name"] == "Team Renamed"
    only_name = await a["owner"].patch(f"/api/v1/workspaces/{ws.id}", json={"name": "Team"})
    assert (
        only_name.json()["name"] == "Team" and only_name.json()["settings"]["default_heldout_fraction"] == 0.2
    )
    assert r.json()["settings"]["default_heldout_fraction"] == 0.2
    assert (await a["admin"].patch(f"/api/v1/workspaces/{ws.id}", json={})).status_code == 422
    bad = {"settings": {"default_heldout_fraction": 0.7}}
    assert (await a["admin"].patch(f"/api/v1/workspaces/{ws.id}", json=bad)).status_code == 422
    # delete: owner only, blocked while runs are active
    assert (await a["admin"].delete(f"/api/v1/workspaces/{ws.id}")).status_code == 403
    run_id = await _make_run(ctx, ws.id, t["users"]["member"].id, RunStatus.RUNNING)
    r = await a["owner"].delete(f"/api/v1/workspaces/{ws.id}")
    assert r.status_code == 409 and r.json()["code"] == "workspace_not_empty"
    await ctx.execute(sa.update(Run).where(Run.id == run_id).values(status=RunStatus.SUCCEEDED))
    pat = await a["member"].post(
        "/api/v1/auth/tokens", json={"name": "t", "workspace_id": str(ws.id), "scopes": ["runs:read"]}
    )
    assert (await a["owner"].delete(f"/api/v1/workspaces/{ws.id}")).status_code == 204
    assert (await a["owner"].get(f"/api/v1/workspaces/{ws.id}")).status_code == 404
    assert (await a["owner"].get("/api/v1/workspaces")).json()["items"] == []
    revoked = await ctx.scalar(
        sa.select(ApiToken.revoked_at).where(ApiToken.id == uuid.UUID(pat.json()["id"]))
    )
    assert revoked is not None


async def _make_run(
    ctx: Ctx, ws_id: uuid.UUID, user_id: uuid.UUID, status: RunStatus, gpu_seconds: float = 0
) -> uuid.UUID:
    async with ctx.session() as s:
        ds = Dataset(workspace_id=ws_id, name="d", slug=f"d{uuid.uuid4().hex[:6]}", created_by=user_id)
        s.add(ds)
        await s.flush()
        dv = DatasetVersion(dataset_id=ds.id, version=1, source=DatasetSource.UPLOAD, size_bytes=1000)
        s.add(dv)
        await s.flush()
        n = (
            await s.execute(
                sa.select(sa.func.coalesce(sa.func.max(Run.number), 0)).where(Run.workspace_id == ws_id)
            )
        ).scalar_one()
        run = Run(
            workspace_id=ws_id,
            number=n + 1,
            name="r",
            created_by=user_id,
            dataset_version_id=dv.id,
            policy_type="act",
            config={},
            heldout_episodes=[],
            train_episodes=[0],
            seed=1,
            total_steps=10,
            status=status,
            gpu_seconds=gpu_seconds,
            finished_at=datetime.now(UTC) if status == RunStatus.SUCCEEDED else None,
        )
        s.add(run)
        await s.commit()
        return run.id


async def test_member_role_matrix(ctx: Ctx) -> None:
    t = await _team(ctx)
    ws, u, a = t["ws"], t["users"], t["api"]
    url = f"/api/v1/workspaces/{ws.id}/members"
    members = (await a["viewer"].get(url)).json()["items"]
    assert [m["email"] for m in members] == [
        "admin@example.com",
        "member@example.com",
        "owner@example.com",
        "viewer@example.com",
    ]
    assert next(m for m in members if m["role"] == "owner")["mfa_enabled"] is True

    async def set_role(actor: str, target: str, role: str) -> Any:
        return await a[actor].patch(f"{url}/{u[target].id}", json={"role": role})

    assert (await set_role("member", "viewer", "member")).status_code == 403
    assert (await set_role("viewer", "member", "viewer")).status_code == 403
    assert (await set_role("admin", "owner", "member")).status_code == 403  # admins cannot touch owners
    assert (await set_role("admin", "member", "admin")).status_code == 403  # admins cannot grant admin
    r = await set_role("admin", "viewer", "member")
    assert r.status_code == 200 and r.json()["role"] == "member"
    r = await set_role("owner", "member", "admin")
    assert r.status_code == 409 and r.json()["code"] == "mfa_required_by_role"
    assert (await set_role("owner", "admin", "admin")).status_code == 200  # no-op
    r = await set_role("owner", "owner", "admin")
    assert r.status_code == 409 and r.json()["code"] == "last_owner"
    assert (await set_role("owner", "admin", "owner")).status_code == 200
    assert (await set_role("owner", "owner", "member")).status_code == 200  # another owner exists now
    assert (await a["admin"].patch(f"{url}/{uuid.uuid4()}", json={"role": "viewer"})).status_code == 404
    r = await a["admin"].patch(f"{url}/{u['viewer'].id}", json={"role": "superuser"})
    assert r.status_code == 400 and r.json()["errors"]
    changes = await ctx.scalar(
        sa.select(sa.func.count()).select_from(AuditEvent).where(AuditEvent.action == "member.role_changed")
    )
    assert changes == 3


async def test_demote_to_viewer_revokes_write_pats(ctx: Ctx) -> None:
    t = await _team(ctx)
    ws, u, a = t["ws"], t["users"], t["api"]
    w = await a["member"].post(
        "/api/v1/auth/tokens", json={"name": "w", "workspace_id": str(ws.id), "scopes": ["runs:write"]}
    )
    rd = await a["member"].post(
        "/api/v1/auth/tokens", json={"name": "r", "workspace_id": str(ws.id), "scopes": ["runs:read"]}
    )
    await a["admin"].patch(f"/api/v1/workspaces/{ws.id}/members/{u['member'].id}", json={"role": "viewer"})
    assert await ctx.scalar(sa.select(ApiToken.revoked_at).where(ApiToken.id == uuid.UUID(w.json()["id"])))
    assert (
        await ctx.scalar(sa.select(ApiToken.revoked_at).where(ApiToken.id == uuid.UUID(rd.json()["id"])))
        is None
    )


async def test_remove_member_and_leave(ctx: Ctx) -> None:
    t = await _team(ctx)
    ws, u, a = t["ws"], t["users"], t["api"]
    url = f"/api/v1/workspaces/{ws.id}/members"
    pat = await a["member"].post(
        "/api/v1/auth/tokens", json={"name": "p", "workspace_id": str(ws.id), "scopes": ["runs:read"]}
    )
    assert (await a["viewer"].delete(f"{url}/{u['member'].id}")).status_code == 403
    assert (await a["admin"].delete(f"{url}/{u['owner'].id}")).status_code == 403
    r = await a["owner"].delete(f"{url}/{u['owner'].id}")
    assert r.status_code == 409 and r.json()["code"] == "last_owner"
    assert (await a["admin"].delete(f"{url}/{u['member'].id}")).status_code == 204
    assert await ctx.scalar(sa.select(ApiToken.revoked_at).where(ApiToken.id == uuid.UUID(pat.json()["id"])))
    assert (await a["member"].get(f"/api/v1/workspaces/{ws.id}")).status_code == 404
    assert (await a["viewer"].delete(f"{url}/{u['viewer'].id}")).status_code == 204  # leave
    assert (await a["admin"].delete(f"{url}/{uuid.uuid4()}")).status_code == 404
    left = await ctx.scalar(
        sa.select(sa.func.count()).select_from(Membership).where(Membership.workspace_id == ws.id)
    )
    assert left == 2


async def test_invite_flow_new_user(ctx: Ctx) -> None:
    t = await _team(ctx)
    ws, a = t["ws"], t["api"]
    url = f"/api/v1/workspaces/{ws.id}/invites"
    assert (
        await a["member"].post(url, json={"email": "new@example.com", "role": "member"})
    ).status_code == 403
    r = await a["admin"].post(url, json={"email": "new@example.com", "role": "admin"})
    assert r.status_code == 403
    r = await a["admin"].post(url, json={"email": "member@example.com", "role": "viewer"})
    assert r.status_code == 409 and r.json()["code"] == "member_exists"
    r = await a["admin"].post(url, json={"email": "owner2@example.com", "role": "owner"})
    assert r.status_code == 422
    r = await a["admin"].post(url, json={"email": "New@Example.com", "role": "member"})
    assert r.status_code == 201, r.text
    inv = r.json()
    assert (
        inv["status"] == "pending" and inv["email"] == "new@example.com" and inv["invited_by"]["display_name"]
    )
    assert inv["accept_url"].startswith("https://robot.example.com/invite#token=")
    token = token_from(inv["accept_url"])
    stored = await ctx.scalar(sa.select(Invite.token_hash).where(Invite.id == uuid.UUID(inv["id"])))
    assert token.encode() not in stored
    listed = (await a["admin"].get(url)).json()["items"]
    assert [i["id"] for i in listed] == [inv["id"]]
    assert (await a["member"].get(url)).status_code == 403

    anon = ctx.client()
    pv = await anon.get(f"/api/v1/auth/invites/{token}")
    assert pv.status_code == 200
    assert pv.json() == {
        "workspace_name": ws.name,
        "email": "new@example.com",
        "role": "member",
        "invited_by": "Admin",
        "expires_at": inv["expires_at"],
        "account_exists": False,
    }
    assert (await anon.get(f"/api/v1/auth/invites/{'z' * 43}")).json()["code"] == "invite_invalid"
    weak = await anon.post(
        "/api/v1/auth/register-invite",
        csrf=False,
        json={"invite_token": token, "display_name": "Newbie", "password": "aaaaaaaaaaaa"},
    )
    assert weak.json()["code"] == "password_too_weak"
    r = await anon.post(
        "/api/v1/auth/register-invite",
        csrf=False,
        json={
            "invite_token": token,
            "display_name": "Newbie",
            "password": "Brand-New-Pass-77",
            "locale": "en",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "ok" and r.json()["user"]["email_verified"] is True
    me = (await anon.get("/api/v1/auth/me")).json()
    assert me["memberships"][0]["role"] == "member" and me["user"]["locale"] == "en"
    again = await ctx.client().post(
        "/api/v1/auth/register-invite",
        csrf=False,
        json={"invite_token": token, "display_name": "X", "password": "Brand-New-Pass-77"},
    )
    assert again.status_code == 410 and again.json()["code"] == "gone"
    assert (await anon.get(f"/api/v1/auth/invites/{token}")).status_code == 410


async def test_invite_existing_user_accept_and_errors(ctx: Ctx) -> None:
    t = await _team(ctx)
    ws, a = t["ws"], t["api"]
    url = f"/api/v1/workspaces/{ws.id}/invites"
    ext = await ctx.create_user("ext@example.com")
    stranger = await ctx.create_user("stranger@example.com")
    inv = (await a["owner"].post(url, json={"email": "ext@example.com", "role": "admin"})).json()
    token = token_from(inv["accept_url"])
    anon = ctx.client()
    assert (await anon.get(f"/api/v1/auth/invites/{token}")).json()["account_exists"] is True
    r = await anon.post(
        "/api/v1/auth/register-invite",
        csrf=False,
        json={"invite_token": token, "display_name": "Ext", "password": "Brand-New-Pass-77"},
    )
    assert r.status_code == 409 and r.json()["code"] == "email_taken"
    sapi = ctx.client()
    await ctx.login(sapi, stranger.email)
    r = await sapi.post(f"/api/v1/auth/invites/{token}/accept")
    assert r.status_code == 403 and r.json()["code"] == "invite_email_mismatch"
    eapi = ctx.client()
    await ctx.login(eapi, ext.email)
    r = await eapi.post(f"/api/v1/auth/invites/{token}/accept")
    assert r.status_code == 200 and r.json() == {
        "workspace_id": str(ws.id),
        "workspace_slug": "team",
        "workspace_name": ws.name,
        "role": "admin",
    }
    # admin role without 2FA => enrolment gate
    assert (await eapi.get("/api/v1/workspaces")).json()["code"] == "mfa_enrollment_required"
    # member_exists on a second invite for an existing member
    inv2 = (await a["owner"].post(url, json={"email": "stranger@example.com", "role": "viewer"})).json()
    tok2 = token_from(inv2["accept_url"])
    await ctx.execute(
        sa.update(Invite)
        .where(Invite.id == uuid.UUID(inv2["id"]))
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    r = await sapi.post(f"/api/v1/auth/invites/{tok2}/accept")
    assert r.status_code == 410 and r.json()["code"] == "invite_expired"


async def test_revoke_and_resend_invite(ctx: Ctx) -> None:
    t = await _team(ctx)
    ws, a = t["ws"], t["api"]
    url = f"/api/v1/workspaces/{ws.id}/invites"
    first = (await a["admin"].post(url, json={"email": "z@example.com", "role": "viewer"})).json()
    second = (await a["admin"].post(url, json={"email": "z@example.com", "role": "member"})).json()
    # re-inviting the same email supersedes the previous invite
    assert (
        await ctx.client().get(f"/api/v1/auth/invites/{token_from(first['accept_url'])}")
    ).status_code == 404
    r = await a["admin"].post(f"{url}/{second['id']}/resend")
    assert r.status_code == 200
    new_tok = token_from(r.json()["accept_url"])
    assert new_tok != token_from(second["accept_url"])
    assert (
        await ctx.client().get(f"/api/v1/auth/invites/{token_from(second['accept_url'])}")
    ).status_code == 404
    assert (await ctx.client().get(f"/api/v1/auth/invites/{new_tok}")).status_code == 200
    assert (await a["admin"].delete(f"{url}/{second['id']}")).status_code == 204
    assert (await a["admin"].delete(f"{url}/{second['id']}")).status_code == 404
    assert (await a["admin"].post(f"{url}/{second['id']}/resend")).status_code == 404
    assert (await ctx.client().get(f"/api/v1/auth/invites/{new_tok}")).json()["code"] == "invite_invalid"
    adm = (await a["owner"].post(url, json={"email": "boss@example.com", "role": "admin"})).json()
    assert (await a["admin"].post(f"{url}/{adm['id']}/resend")).status_code == 403
    assert (await a["admin"].get(url)).json()["items"][0]["id"] == adm["id"]


async def test_invite_email_delivery_hides_accept_url(make_ctx: Any) -> None:
    ctx: Ctx = await make_ctx(
        email_provider="smtp", smtp_host="127.0.0.1", smtp_port=1, smtp_starttls=False, email_timeout_s=1
    )
    root, api = await _admin(ctx)
    ws = await ctx.create_workspace("mail", {root.id: WorkspaceRole.OWNER})
    r = await api.post(
        f"/api/v1/workspaces/{ws.id}/invites", json={"email": "m@example.com", "role": "member"}
    )
    # SMTP is unreachable: the invite is still created, delivery failure is logged, link not leaked
    assert r.status_code == 201 and r.json()["accept_url"] is None
    cfg = (await ctx.client().get("/api/v1/auth/config")).json()
    assert cfg["email_delivery_enabled"] is True


async def test_usage(ctx: Ctx) -> None:
    t = await _team(ctx)
    ws, u, a = t["ws"], t["users"], t["api"]
    await _make_run(ctx, ws.id, u["member"].id, RunStatus.RUNNING)
    await _make_run(ctx, ws.id, u["member"].id, RunStatus.QUEUED)
    done = await _make_run(ctx, ws.id, u["admin"].id, RunStatus.SUCCEEDED, gpu_seconds=7200)
    # QC-backend-03: GPU hours count only time spent in an active status this month (status events).
    now = datetime.now(UTC)
    if now - timedelta(hours=2, minutes=5) < now.replace(day=1, hour=0, minute=0, second=0, microsecond=0):
        pytest.skip("too close to the month boundary for a 2 h window")
    async with ctx.session() as s:
        for seq, (to, ago) in enumerate(
            [("running", timedelta(hours=2, minutes=1)), ("succeeded", timedelta())], 1
        ):
            s.add(
                RunEvent(
                    run_id=done, seq=seq, type="status", attempt=1, data={"to": to}, created_at=now - ago
                )
            )
        s.add(
            Quota(
                workspace_id=ws.id,
                user_id=None,
                max_concurrent_runs=2,
                max_queued_runs=5,
                gpu_hours_per_month=50,
                storage_bytes=10**12,
                max_upload_bytes=10**10,
            )
        )
        s.add(
            Quota(
                workspace_id=ws.id,
                user_id=u["member"].id,
                max_concurrent_runs=3,
                max_queued_runs=5,
                gpu_hours_per_month=10,
                storage_bytes=10**12,
                max_upload_bytes=10**10,
            )
        )
        await s.commit()
    r = await a["member"].get(f"/api/v1/workspaces/{ws.id}/usage")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workspace"]["active_runs"] == 1 and body["workspace"]["queued_runs"] == 1
    assert body["workspace"]["gpu_hours_this_month"] == pytest.approx(2.0)
    assert body["workspace"]["storage_bytes_used"] == 3000
    assert body["workspace"]["limits"]["max_concurrent_runs"] == 2
    assert body["me"]["limits"]["max_concurrent_runs"] == 3 and body["me"]["active_runs"] == 1
    assert body["me"]["fair_share_gpu_hours_7d"] == 0
    adm = (await a["admin"].get(f"/api/v1/workspaces/{ws.id}/usage")).json()
    assert adm["me"]["limits"]["max_concurrent_runs"] == 2
    assert 1.9 < adm["me"]["fair_share_gpu_hours_7d"] <= 2.0
    # defaults when no quota rows exist
    other = await ctx.create_workspace("noquota", {u["member"].id: WorkspaceRole.MEMBER})
    d = (await a["member"].get(f"/api/v1/workspaces/{other.id}/usage")).json()
    assert (
        d["workspace"]["limits"]["max_concurrent_runs"] == 1
        and d["workspace"]["limits"]["storage_bytes"] == 200 * 1024**3
    )


async def test_workspace_event_stream(ctx: Ctx) -> None:
    """Real uvicorn on an ephemeral loopback port (ASGITransport buffers streaming bodies)."""
    import socket

    import httpx
    import uvicorn

    from app.core import events

    t = await _team(ctx)
    ws, u = t["ws"], t["users"]
    run_id = await _make_run(ctx, ws.id, u["member"].id, RunStatus.QUEUED)
    cookies = t["api"]["viewer"].http.cookies
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    assert port not in (8000, 18000)
    server = uvicorn.Server(uvicorn.Config(ctx.app, log_level="warning", lifespan="off"))
    serve = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        while not server.started:  # noqa: ASYNC110 - uvicorn exposes a flag, not an event
            await asyncio.sleep(0.05)
        base = f"http://127.0.0.1:{port}"
        got: list[tuple[str, dict[str, Any]]] = []
        jar = httpx.Cookies()
        for c in cookies.jar:
            jar.set(c.name, c.value or "")
        async with httpx.AsyncClient(base_url=base, cookies=jar, timeout=15) as client:
            async with httpx.AsyncClient(base_url=base, timeout=5) as anon:
                r = await anon.get(f"/api/v1/workspaces/{ws.id}/events")
                assert r.status_code == 401

            async def consume() -> None:
                async with client.stream("GET", f"/api/v1/workspaces/{ws.id}/events") as resp:
                    assert resp.status_code == 200
                    assert resp.headers["content-type"].startswith("text/event-stream")
                    assert resp.headers["x-accel-buffering"] == "no"
                    event = None
                    async for line in resp.aiter_lines():
                        if line.startswith("event:"):
                            event = line.split(":", 1)[1].strip()
                        elif line.startswith("data:") and event:
                            got.append((event, json.loads(line.split(":", 1)[1])))
                            return

            task = asyncio.create_task(consume())
            await asyncio.sleep(1.0)
            data = {
                "kind": "status",
                "run_id": str(run_id),
                "from": "queued",
                "to": "preparing",
                "ts": "2026-11-15T00:00:00Z",
            }
            redis = ctx.svc.redis
            await redis.publish(events.workspace_channel(ws.id), b"not json")  # skipped by the stream
            await redis.publish(events.workspace_channel(ws.id), b'{"no_event": 1}')
            async with ctx.session() as s:
                seq = await events.publish_run_event(run_id, "status", data, True, db=s)
                await s.commit()
            assert seq == 1
            await asyncio.wait_for(task, timeout=10)
        assert got == [("run.status", data)]
    finally:
        server.should_exit = True
        await asyncio.wait_for(serve, timeout=10)


def test_invite_status_values() -> None:
    from app.workspaces.invites import invite_status

    now = datetime.now(UTC)
    base: dict[str, Any] = {
        "workspace_id": uuid.uuid4(),
        "email": "a@example.com",
        "role": WorkspaceRole.MEMBER,
        "token_hash": b"x" * 32,
    }
    assert invite_status(Invite(**base, expires_at=now + timedelta(hours=1)), now) == "pending"
    assert invite_status(Invite(**base, expires_at=now - timedelta(seconds=1)), now) == "expired"
    assert invite_status(Invite(**base, expires_at=now, revoked_at=now), now) == "revoked"
    assert invite_status(Invite(**base, expires_at=now, accepted_at=now), now) == "accepted"


async def test_accept_invite_when_already_member(ctx: Ctx) -> None:
    from app.core.crypto import sha256

    t = await _team(ctx)
    ws = t["ws"]
    token = "m" * 43
    async with ctx.session() as s:
        s.add(
            Invite(
                workspace_id=ws.id,
                email="member@example.com",
                role=WorkspaceRole.VIEWER,
                token_hash=sha256(token),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await s.commit()
    r = await t["api"]["member"].post(f"/api/v1/auth/invites/{token}/accept")
    assert r.status_code == 409 and r.json()["code"] == "member_exists"
