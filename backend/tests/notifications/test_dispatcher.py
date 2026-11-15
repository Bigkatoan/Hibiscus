"""Dispatcher: fan-out, per-kind delivery to a local HTTPS server, retries/backoff, permanent
failures, SSRF at send time (DNS rebinding), email (smtp + none), leader election, in-app SSE."""

from __future__ import annotations

import asyncio
import json
import socket
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import uvicorn
from aiosmtpd.controller import Controller
from sqlalchemy import select, text

from app.core.email import SmtpEmailSender
from app.core.events import workspace_channel
from app.db import models as m
from app.main import create_app
from app.notifications.channels import encrypt_target
from app.notifications.dispatcher import LOCK_ID, dispatcher_loop
from app.notifications.router import setup_app
from tests.auth.fixtures import Infra, make_settings
from tests.integration.authn import add_member, create_workspace, session_headers
from tests.notifications.conftest import NCtx, build, notify_settings
from tests.notifications.helpers import HOOK_HOST, TEST_DNS, HookServer, fake_dns


async def _channel(
    c: NCtx, kind: str, target: str, events: list[str], user: uuid.UUID | None = None
) -> uuid.UUID:
    uid = user or c.user
    svc = c.app.state.services
    async with svc.db.sessionmaker() as db:
        ch = m.NotificationChannel(
            id=uuid.uuid4(), user_id=uid, kind=m.NotificationChannelKind(kind), events=events
        )
        ch.config_enc = encrypt_target(svc.cipher, uid, ch.id, target)
        db.add(ch)
        await db.commit()
        return ch.id


async def _notify(
    c: NCtx,
    kind: str,
    params: dict[str, Any] | None = None,
    *,
    ws: uuid.UUID | None = None,
    user: uuid.UUID | None = None,
    age_s: float = 0,
) -> uuid.UUID:
    """What the train worker does (runner._notify): a bare INSERT."""
    async with c.app.state.services.db.sessionmaker() as db:
        n = m.Notification(
            user_id=user or c.user,
            workspace_id=ws,
            kind=kind,
            params=params or {"run_number": 7, "run_id": str(uuid.uuid4())},
            link="/runs/abc",
            created_at=datetime.now(UTC) - timedelta(seconds=age_s),
        )
        db.add(n)
        await db.commit()
        return n.id


async def _deliveries(c: NCtx) -> list[m.NotificationDelivery]:
    async with c.app.state.services.db.sessionmaker() as db:
        return list(
            (
                await db.execute(select(m.NotificationDelivery).order_by(m.NotificationDelivery.created_at))
            ).scalars()
        )


async def test_fan_out_and_delivery_per_kind(nctx: NCtx) -> None:
    ws = await create_workspace(nctx.app, {nctx.user: m.WorkspaceRole.MEMBER})
    async with nctx.app.state.services.db.sessionmaker() as db:
        w = await db.get(m.Workspace, ws)
        assert w is not None
        slug = w.slug
        u = await db.get(m.User, nctx.user)
        assert u is not None
        u.locale = "en"
        await db.commit()
    await _channel(nctx, "webhook", nctx.hook.url("/generic"), ["run.succeeded", "run.failed"])
    await _channel(nctx, "discord", nctx.hook.url("/api/webhooks/1/tok"), ["run.failed"])
    await _channel(
        nctx, "telegram", "123456789:AAH-abcdefghijklmnopqrstuvwxyz_0123:-1001234567890", ["run.failed"]
    )
    off = await _channel(nctx, "webhook", nctx.hook.url("/disabled"), ["run.failed"])
    async with nctx.app.state.services.db.sessionmaker() as db:
        ch = await db.get(m.NotificationChannel, off)
        assert ch is not None
        ch.enabled = False
        await db.commit()
    await _channel(nctx, "webhook", nctx.hook.url("/other-user"), ["run.failed"], user=nctx.other)
    nid = await _notify(nctx, "run.failed", {"run_number": 42, "error_code": "oom\n@everyone"}, ws=ws)
    await _notify(nctx, "model.failed", ws=ws)  # nobody subscribes to it

    res = await nctx.state.dispatcher.run_once()
    assert res["fanned_out"] == 2 and res["sent"] == 3, res
    by_path = {r.path: r for r in nctx.hook.received}
    assert set(by_path) == {
        "/generic",
        "/api/webhooks/1/tok",
        "/tg/bot123456789:AAH-abcdefghijklmnopqrstuvwxyz_0123/sendMessage",
    }
    generic = by_path["/generic"].body
    assert generic["event"] == "run.failed" and generic["notification"]["id"] == str(nid)
    assert generic["title"] == "Run #42 failed (oom @everyone)"  # control chars flattened
    assert generic["url"] == f"https://robot.example.com/w/{slug}/runs/abc"
    discord = by_path["/api/webhooks/1/tok"].body
    assert discord["allowed_mentions"] == {"parse": []} and discord["content"].startswith("Run #42 failed")
    tg = by_path["/tg/bot123456789:AAH-abcdefghijklmnopqrstuvwxyz_0123/sendMessage"].body
    assert tg["chat_id"] == "-1001234567890" and "parse_mode" not in tg
    ds = await _deliveries(nctx)
    assert len(ds) == 3 and {d.status for d in ds} == {"sent"} and all(d.attempts == 1 for d in ds)
    async with nctx.app.state.services.db.sessionmaker() as db:
        assert all(n.dispatched_at is not None for n in (await db.execute(select(m.Notification))).scalars())
    # idempotent: nothing new on the next pass
    assert await nctx.state.dispatcher.run_once() == {"fanned_out": 0}
    assert len(nctx.hook.received) == 3


async def test_retry_backoff_then_success_and_permanent_failures(nctx: NCtx) -> None:
    calls = {"n": 0}

    def flaky(_p: str) -> tuple[int, dict[str, str], bytes]:
        calls["n"] += 1
        return (503, {}, b"") if calls["n"] < 3 else (200, {}, b"")

    nctx.hook.responder = flaky
    await _channel(nctx, "webhook", nctx.hook.url("/flaky"), ["run.succeeded"])
    await _notify(nctx, "run.succeeded")
    d = nctx.state.dispatcher
    assert (await d.run_once()).get("retry") == 1
    (row,) = await _deliveries(nctx)
    assert row.status == "pending" and row.attempts == 1 and row.last_error == "HTTP 503"
    assert (await d.run_once()).get("retry") == 1
    assert (await d.run_once()).get("sent") == 1
    (row,) = await _deliveries(nctx)
    assert row.status == "sent" and row.attempts == 3 and row.last_error is None and row.sent_at

    # backoff schedule (base 30 s, x4, capped)
    d.settings.backoff_base_s, d.settings.backoff_max_s = 30.0, 3600.0
    assert [d.backoff_s(a) for a in (1, 2, 3, 4, 5)] == [30.0, 120.0, 480.0, 1920.0, 3600.0]
    d.settings.backoff_base_s = 0.0


async def test_max_attempts_and_non_retryable(nctx: NCtx) -> None:
    nctx.hook.responder = lambda p: (500, {}, b"") if p == "/down" else (410, {}, b"")
    nctx.state.settings.max_attempts = 3
    await _channel(nctx, "webhook", nctx.hook.url("/down"), ["run.failed"])
    await _channel(nctx, "webhook", nctx.hook.url("/gone"), ["run.failed"])
    await _notify(nctx, "run.failed")
    for _ in range(4):
        await nctx.state.dispatcher.run_once()
    ds = {d.last_error: d for d in await _deliveries(nctx)}
    assert ds["HTTP 500"].status == "failed" and ds["HTTP 500"].attempts == 3
    assert ds["HTTP 410"].status == "failed" and ds["HTTP 410"].attempts == 1
    assert [r.path for r in nctx.hook.received].count("/down") == 3


async def test_redirect_is_permanent_failure(nctx: NCtx) -> None:
    nctx.hook.responder = lambda p: (
        (301, {"Location": nctx.hook.url("/elsewhere")}, b"") if p == "/moved" else (200, {}, b"")
    )
    await _channel(nctx, "webhook", nctx.hook.url("/moved"), ["run.failed"])
    await _notify(nctx, "run.failed")
    await nctx.state.dispatcher.run_once()
    (row,) = await _deliveries(nctx)
    assert row.status == "failed" and "redirect" in (row.last_error or "")
    assert [r.path for r in nctx.hook.received] == ["/moved"]


async def test_dns_rebinding_blocked_at_send_time(nctx: NCtx) -> None:
    dns = dict(TEST_DNS)
    nctx.state.policy.resolver = fake_dns(dns)
    await _channel(nctx, "webhook", "https://rebind.test/x", ["run.failed"])  # was public when created
    dns["rebind.test"] = ["169.254.169.254"]
    await _notify(nctx, "run.failed")
    await nctx.state.dispatcher.run_once()
    (row,) = await _deliveries(nctx)
    assert row.status == "failed" and row.last_error == "target rejected: address_not_allowed"


async def test_old_notifications_not_replayed(nctx: NCtx) -> None:
    await _channel(nctx, "webhook", nctx.hook.url("/x"), ["run.failed"])
    await _notify(nctx, "run.failed", age_s=2 * 86400)
    assert (await nctx.state.dispatcher.run_once()) == {"fanned_out": 1}
    assert nctx.hook.received == [] and await _deliveries(nctx) == []


async def test_email_none_provider_fails_without_retry(nctx: NCtx) -> None:
    await _channel(nctx, "email", "owner@example.com", ["run.succeeded"])
    await _notify(nctx, "run.succeeded")
    await nctx.state.dispatcher.run_once()
    (row,) = await _deliveries(nctx)
    assert row.status == "failed" and row.attempts == 1 and "disabled" in (row.last_error or "")


async def test_email_smtp_delivery(containers: Infra, hook: HookServer) -> None:
    received: list[Any] = []

    class Handler:
        async def handle_DATA(self, server: Any, session: Any, envelope: Any) -> str:  # noqa: N802 - aiosmtpd API
            received.append(envelope)
            return "250 OK"

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    ctl = Controller(Handler(), hostname="127.0.0.1", port=port)
    ctl.start()
    sender = SmtpEmailSender(
        "127.0.0.1", port, "Hibiscus <no-reply@example.com>", starttls=False, timeout_s=5
    )
    c = await build(containers, hook, {}, email=sender)
    try:
        await _channel(c, "email", "owner@example.com", ["run.succeeded"])
        await _notify(c, "run.succeeded", {"run_number": 3})
        assert (await c.state.dispatcher.run_once()).get("sent") == 1
        assert received and received[0].rcpt_tos == ["owner@example.com"]
        raw = received[0].content.decode()
        assert "Run #3" in raw and "robot.example.com/runs/abc" in raw
        # account email changed -> the old channel target is no longer delivered to
        async with c.app.state.services.db.sessionmaker() as db:
            u = await db.get(m.User, c.user)
            assert u is not None
            u.email = "new@example.com"
            await db.commit()
        await _notify(c, "run.succeeded")
        await c.state.dispatcher.run_once()
        assert len(received) == 1
        assert [d.status for d in await _deliveries(c)] == ["sent", "failed"]
    finally:
        ctl.stop()
        await c.api.aclose()
        await c.app.state.services.redis.aclose()
        await c.app.state.services.db.dispose()


async def test_leader_election_no_double_send(containers: Infra, hook: HookServer) -> None:
    c = await build(containers, hook, {"poll_interval_s": 0.05})
    other_app = create_app(make_settings(extra_routers=["app.notifications.router"]))
    other = setup_app(other_app, notify_settings(hook, poll_interval_s=0.05), resolver=fake_dns(TEST_DNS))
    try:
        await _channel(c, "webhook", hook.url("/once"), ["run.failed"])
        for _ in range(8):
            await _notify(c, "run.failed")
        tasks = [
            asyncio.create_task(dispatcher_loop(c.state.dispatcher)),
            asyncio.create_task(dispatcher_loop(other.dispatcher)),
        ]
        try:
            for _ in range(100):
                if len(hook.received) >= 8:
                    break
                await asyncio.sleep(0.05)
            await asyncio.sleep(0.5)  # give a hypothetical second sender time to misbehave
            async with c.app.state.services.db.sessionmaker() as db:
                holders = (
                    await db.execute(
                        text(
                            "SELECT count(*) FROM pg_locks"
                            " WHERE locktype = 'advisory' AND objid = :k AND granted"
                        ),
                        {"k": LOCK_ID},
                    )
                ).scalar_one()
            assert holders == 1  # exactly one leader
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        assert len(hook.received) == 8
        assert {d.status for d in await _deliveries(c)} == {"sent"}
    finally:
        await c.api.aclose()
        for a in (c.app, other_app):
            await a.state.services.redis.aclose()
            await a.state.services.db.dispose()


async def test_in_app_event_addressed_to_user_only(nctx: NCtx) -> None:
    """Real uvicorn (ASGITransport buffers SSE): the owner gets ``notification``, the other member
    of the same workspace does not (they only see the subsequent workspace-wide event)."""
    ws = await create_workspace(nctx.app, {nctx.user: m.WorkspaceRole.MEMBER})
    await add_member(nctx.app, ws, nctx.other, m.WorkspaceRole.MEMBER)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    assert port not in (8000, 18000)
    server = uvicorn.Server(uvicorn.Config(nctx.app, log_level="warning", lifespan="off"))
    serve = asyncio.create_task(server.serve(sockets=[sock]))
    got: dict[str, list[tuple[str, dict[str, Any]]]] = {"me": [], "other": []}
    try:
        while not server.started:  # noqa: ASYNC110 - uvicorn exposes a flag, not an event
            await asyncio.sleep(0.05)

        async def consume(who: str, uid: uuid.UUID) -> None:
            h = await session_headers(nctx.app, uid)
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=15) as client:
                async with client.stream("GET", f"/api/v1/workspaces/{ws}/events", headers=h) as resp:
                    assert resp.status_code == 200
                    event = None
                    async for line in resp.aiter_lines():
                        if line.startswith("event:"):
                            event = line.split(":", 1)[1].strip()
                        elif line.startswith("data:") and event and event != "heartbeat":
                            got[who].append((event, json.loads(line.split(":", 1)[1])))
                            if event == "run.status":
                                return

        tasks = [
            asyncio.create_task(consume("me", nctx.user)),
            asyncio.create_task(consume("other", nctx.other)),
        ]
        await asyncio.sleep(1.0)
        nid = await _notify(nctx, "run.succeeded", ws=ws)
        await nctx.state.dispatcher.run_once()
        await asyncio.sleep(0.5)
        r = nctx.app.state.services.redis
        await r.publish(
            workspace_channel(ws), json.dumps({"event": "run.status", "data": {"kind": "status"}})
        )
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
    finally:
        server.should_exit = True
        await serve
    assert [e for e, _ in got["other"]] == ["run.status"]
    assert [e for e, _ in got["me"]] == ["notification", "run.status"]
    data = got["me"][0][1]
    assert data["id"] == str(nid) and data["kind"] == "run.succeeded" and data["read"] is False


@pytest.mark.parametrize("locale", ["vi", "en"])
async def test_render_locale(nctx: NCtx, locale: str) -> None:
    async with nctx.app.state.services.db.sessionmaker() as db:
        u = await db.get(m.User, nctx.user)
        assert u is not None
        u.locale = locale
        await db.commit()
    await _channel(nctx, "webhook", nctx.hook.url("/l"), ["run.stalled"])
    await _notify(nctx, "run.stalled", {"run_number": 5, "silent_s": 300})
    await nctx.state.dispatcher.run_once()
    text = nctx.hook.received[-1].body["text"]
    expected = (
        "Run #5 có vẻ bị treo (không có log trong 300 giây)"
        if locale == "vi"
        else "Run #5 looks stalled (no output for 300 s)"
    )
    assert text.startswith(expected) and HOOK_HOST not in text
