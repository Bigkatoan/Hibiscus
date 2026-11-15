"""Every ``notifications`` operation with real auth (cookie session + CSRF / PAT), validated
against api/openapi.yaml by ``tests.auth.fixtures.Api``."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.core.audit import verify_chain
from app.db import models as m
from app.notifications.channels import decrypt_target
from tests.auth.fixtures import Infra
from tests.integration.authn import create_user, create_workspace, pat_headers
from tests.integration.test_cross_domain_auth import assert_problem
from tests.notifications.conftest import NCtx, build
from tests.notifications.helpers import HOOK_HOST, HookServer

V1 = "/api/v1"
CH = f"{V1}/users/me/notification-channels"
DISCORD = "https://discord.com/api/webhooks/123456789/secretTOKENabcd"


@pytest.fixture
async def strict(containers: Infra, hook: HookServer) -> AsyncIterator[NCtx]:
    """Production SSRF policy (no allow-listed networks)."""
    c = await build(containers, hook, {"ssrf_allow_cidrs": []})
    try:
        yield c
    finally:
        await c.api.aclose()
        await c.app.state.services.redis.aclose()
        await c.app.state.services.db.dispose()


async def _create(c: NCtx, h: dict[str, str], kind: str, target: str, events: list[str] | None = None) -> Any:
    return await c.api.post(
        CH, headers=h, json={"kind": kind, "target": target, "events": events or ["run.succeeded"]}
    )


async def test_auth_required_and_pat_refused(nctx: NCtx) -> None:
    nid, cid = uuid.uuid4(), uuid.uuid4()
    ops = [
        ("get", CH),
        ("post", CH),
        ("delete", f"{CH}/{cid}"),
        ("post", f"{CH}/{cid}/test"),
        ("get", f"{V1}/notifications"),
        ("post", f"{V1}/notifications/{nid}/read"),
        ("post", f"{V1}/notifications/read-all"),
    ]
    for method, url in ops:
        kw: dict[str, Any] = (
            {"json": {"kind": "email", "target": "x", "events": ["run.failed"]}}
            if (method == "post" and url == CH)
            else {}
        )
        assert_problem(await getattr(nctx.api, method)(url, **kw), 401, "unauthenticated")
    ws = await create_workspace(nctx.app, {nctx.user: m.WorkspaceRole.MEMBER})
    pat = await pat_headers(nctx.app, nctx.user, ws, ["runs:read", "datasets:read", "models:read"])
    for method, url in ops:
        assert_problem(await getattr(nctx.api, method)(url, headers=pat), 403, "forbidden")
    # cookie session without the CSRF header on unsafe methods
    h = await nctx.as_user()
    no_csrf = {"Cookie": h["Cookie"]}
    for method, url in ops:
        if method != "get":
            assert_problem(await getattr(nctx.api, method)(url, headers=no_csrf), 403, "csrf_failed")


async def test_channel_crud_secrets_masked_and_audited(nctx: NCtx) -> None:
    h = await nctx.as_user()
    r = await _create(nctx, h, "discord", DISCORD, ["run.failed", "run.succeeded", "run.failed"])
    assert r.status_code == 201, r.text
    ch = r.json()
    assert ch["kind"] == "discord" and ch["enabled"] is True
    assert ch["events"] == ["run.failed", "run.succeeded"]
    assert ch["target_hint"] == "discord.com/api/webhooks/…/abcd"
    assert "secretTOKEN" not in r.text and "target" not in ch
    hook_url = nctx.hook.url("/generic/secret-path-xyz9")
    r2 = await _create(nctx, h, "webhook", hook_url, ["run.stalled"])
    assert r2.status_code == 201, r2.text
    assert r2.json()["target_hint"] == f"{HOOK_HOST}/…xyz9"
    tg = await _create(nctx, h, "telegram", "123456789:AAH-abcdefghijklmnopqrstuvwxyz_0123:-1001234567890")
    assert tg.status_code == 201, tg.text
    assert tg.json()["target_hint"] == "telegram chat …7890" and "AAH-" not in tg.text
    em = await _create(nctx, h, "email", "Owner@Example.com")
    assert em.status_code == 201, em.text
    assert em.json()["target_hint"] == "o***@example.com"

    lst = await nctx.api.get(CH, headers=h)
    assert lst.status_code == 200
    assert [c["kind"] for c in lst.json()["items"]] == ["discord", "webhook", "telegram", "email"]
    assert "secretTOKEN" not in lst.text and "secret-path" not in lst.text
    # other users see nothing
    other = await nctx.as_user(nctx.other)
    assert (await nctx.api.get(CH, headers=other)).json() == {"items": []}

    svc = nctx.app.state.services
    async with svc.db.sessionmaker() as db:
        row = await db.get(m.NotificationChannel, uuid.UUID(ch["id"]))
        assert row is not None and b"secretTOKEN" not in row.config_enc
        assert decrypt_target(svc.cipher, row.user_id, row.id, row.config_enc) == DISCORD
        audits = list((await db.execute(select(m.AuditEvent).order_by(m.AuditEvent.id))).scalars())
        assert [a.details["op"] for a in audits] == ["notification_channel.created"] * 4
        assert all(a.action == "secret.updated" and a.target_type == "notification_channel" for a in audits)
        assert "secretTOKEN" not in str([a.details for a in audits])

    # delete: other user's channel -> 404, own -> 204, twice -> 404
    assert_problem(await nctx.api.delete(f"{CH}/{ch['id']}", headers=other), 404, "not_found")
    assert (await nctx.api.delete(f"{CH}/{ch['id']}", headers=h)).status_code == 204
    assert_problem(await nctx.api.delete(f"{CH}/{ch['id']}", headers=h), 404, "not_found")
    assert_problem(await nctx.api.delete(f"{CH}/not-a-uuid", headers=h), 400, "bad_request")
    async with svc.db.sessionmaker() as db:
        acts = [a.details["op"] for a in (await db.execute(select(m.AuditEvent))).scalars()]
        assert acts.count("notification_channel.deleted") == 1
        assert await verify_chain(db) == (True, None)


@pytest.mark.parametrize(
    ("kind", "target", "reason"),
    [
        ("webhook", "http://example.com/hook", "https_required"),
        ("webhook", "https://user:pw@public.test/hook", "url_userinfo"),
        ("webhook", "https://127.0.0.1/hook", "address_not_allowed"),
        ("webhook", "https://10.20.30.40/hook", "address_not_allowed"),
        ("webhook", "https://169.254.169.254/latest/meta-data/", "address_not_allowed"),
        ("webhook", "https://[::1]/hook", "address_not_allowed"),
        ("webhook", "https://[::ffff:10.0.0.1]/hook", "address_not_allowed"),
        ("webhook", "https://private.test/hook", "address_not_allowed"),
        ("webhook", "https://mixed.test/hook", "address_not_allowed"),
        ("webhook", "https://cgnat.test/hook", "address_not_allowed"),
        ("webhook", "https://hook.test/hook", "address_not_allowed"),  # 127.0.0.1 without allow-list
        ("webhook", "https://nope.invalid/hook", "dns_failed"),
        ("discord", "https://evil.example/api/webhooks/1/x", "discord_url_invalid"),
        ("discord", "https://discord.com/not-webhooks/1/x", "discord_url_invalid"),
        ("telegram", "123:short", "telegram_target_invalid"),
        ("telegram", "no-colon", "telegram_target_invalid"),
        ("email", "someone-else@example.com", "email_not_own"),
        ("email", "not-an-email", "email_invalid"),
    ],
)
async def test_create_rejects_unsafe_targets(strict: NCtx, kind: str, target: str, reason: str) -> None:
    h = await strict.as_user()
    body = assert_problem(await _create(strict, h, kind, target), 422, "validation_failed")
    assert body["errors"][0]["loc"] == ["body", "target"] and body["errors"][0]["code"] == reason
    async with strict.app.state.services.db.sessionmaker() as db:
        assert (await db.execute(select(m.NotificationChannel))).first() is None


async def test_create_schema_validation(nctx: NCtx) -> None:
    h = await nctx.as_user()
    bad: list[dict[str, Any]] = [
        {"kind": "webhook", "target": "https://public.test/x", "events": []},
        {"kind": "webhook", "target": "https://public.test/x", "events": ["quota.warning"]},
        {"kind": "sms", "target": "x", "events": ["run.failed"]},
        {"kind": "webhook", "target": "https://public.test/x", "events": ["run.failed"], "extra": 1},
        {"kind": "webhook", "target": "https://public.test/" + "a" * 600, "events": ["run.failed"]},
        {"kind": "webhook", "events": ["run.failed"]},
    ]
    for b in bad:
        assert_problem(await nctx.api.post(CH, headers=h, json=b), 422, "validation_failed")


async def test_unverified_email_and_channel_cap(containers: Infra, hook: HookServer) -> None:
    c = await build(containers, hook, {"max_channels_per_user": 2})
    try:
        uid = await create_user(c.app, email="unverified@example.com")
        async with c.app.state.services.db.sessionmaker() as db:
            u = await db.get(m.User, uid)
            assert u is not None
            u.email_verified_at = None
            await db.commit()
        h = await c.as_user(uid)
        body = assert_problem(
            await _create(c, h, "email", "unverified@example.com"), 422, "validation_failed"
        )
        assert body["errors"][0]["code"] == "email_not_verified"
        h = await c.as_user()
        for _ in range(2):
            assert (await _create(c, h, "discord", DISCORD)).status_code == 201
        body = assert_problem(await _create(c, h, "discord", DISCORD), 422, "validation_failed")
        assert body["errors"][0]["code"] == "max_channels"
    finally:
        await c.api.aclose()
        await c.app.state.services.redis.aclose()
        await c.app.state.services.db.dispose()


async def test_test_endpoint_sends_now_and_is_rate_limited(nctx: NCtx) -> None:
    h = await nctx.as_user()
    ch = (await _create(nctx, h, "webhook", nctx.hook.url("/t"))).json()
    r = await nctx.api.post(f"{CH}/{ch['id']}/test", headers=h)
    assert r.status_code == 202, r.text
    got = nctx.hook.received[-1]
    assert got.path == "/t" and got.body["event"] == "test"
    assert got.body["text"].startswith("Thông báo thử")  # default locale vi
    assert got.headers["x-hibiscus-event"] == "test"
    # not found for others, bad id
    other = await nctx.as_user(nctx.other)
    assert_problem(await nctx.api.post(f"{CH}/{ch['id']}/test", headers=other), 404, "not_found")
    # failing target -> problem, the remote body is never echoed
    nctx.hook.responder = lambda _p: (500, {}, b"internal secret stack trace")
    body = assert_problem(await nctx.api.post(f"{CH}/{ch['id']}/test", headers=h), 503, "service_unavailable")
    assert "secret stack" not in str(body) and "HTTP 500" in body["detail"]
    nctx.hook.responder = lambda _p: (200, {}, b"")
    # 5 per minute per user (1 + 1 failing above + 3 more), then 429 with Retry-After
    for _ in range(3):
        assert (await nctx.api.post(f"{CH}/{ch['id']}/test", headers=h)).status_code == 202
    r = await nctx.api.post(f"{CH}/{ch['id']}/test", headers=h)
    assert_problem(r, 429, "rate_limited")
    assert int(r.headers["Retry-After"]) >= 1


async def test_test_endpoint_email_disabled_provider(nctx: NCtx) -> None:
    h = await nctx.as_user()
    ch = (await _create(nctx, h, "email", "owner@example.com")).json()
    body = assert_problem(await nctx.api.post(f"{CH}/{ch['id']}/test", headers=h), 503, "service_unavailable")
    assert "disabled" in body["detail"]
    outbox = nctx.app.state.services.email.outbox
    assert outbox == []  # never handed to the "none" provider as if delivered


async def _seed_notifications(
    c: NCtx, n: int, user: uuid.UUID, ws: uuid.UUID | None = None
) -> list[uuid.UUID]:
    ids = []
    base = datetime.now(UTC) - timedelta(minutes=10)
    async with c.app.state.services.db.sessionmaker() as db:
        for i in range(n):
            row = m.Notification(
                user_id=user,
                workspace_id=ws,
                kind="run.succeeded",
                params={"run_number": i, "run_id": str(uuid.uuid4())},
                link=f"/runs/{uuid.uuid4()}",
                created_at=base + timedelta(seconds=i // 2),  # pairs share a timestamp (tie-break by id)
                dispatched_at=base,
            )
            db.add(row)
            await db.flush()
            ids.append(row.id)
        await db.commit()
    return ids


async def test_list_paginate_mark_read(nctx: NCtx) -> None:
    ws = await create_workspace(nctx.app, {nctx.user: m.WorkspaceRole.MEMBER})
    mine = await _seed_notifications(nctx, 5, nctx.user, ws)
    theirs = await _seed_notifications(nctx, 2, nctx.other)
    h = await nctx.as_user()
    r = await nctx.api.get(f"{V1}/notifications", headers=h, params={"limit": 2})
    assert r.status_code == 200
    page = r.json()
    assert page["unread_count"] == 5 and len(page["items"]) == 2 and page["next_cursor"]
    seen = [i["id"] for i in page["items"]]
    cursor = page["next_cursor"]
    while cursor:
        p = (
            await nctx.api.get(f"{V1}/notifications", headers=h, params={"limit": 2, "cursor": cursor})
        ).json()
        seen += [i["id"] for i in p["items"]]
        cursor = p["next_cursor"]
    assert sorted(seen) == sorted(str(i) for i in mine) and len(seen) == len(set(seen)) == 5
    full = (await nctx.api.get(f"{V1}/notifications", headers=h)).json()["items"]
    stamps = [(i["created_at"], i["id"]) for i in full]
    assert stamps == sorted(stamps, reverse=True)  # newest first, stable
    assert (
        full[0]["workspace_id"] == str(ws)
        and full[0]["read"] is False
        and full[0]["params"]["run_number"] == 4
    )

    assert (await nctx.api.post(f"{V1}/notifications/{mine[0]}/read", headers=h)).status_code == 204
    assert (
        await nctx.api.post(f"{V1}/notifications/{mine[0]}/read", headers=h)
    ).status_code == 204  # idempotent
    assert_problem(await nctx.api.post(f"{V1}/notifications/{theirs[0]}/read", headers=h), 404, "not_found")
    assert_problem(
        await nctx.api.post(f"{V1}/notifications/{uuid.uuid4()}/read", headers=h), 404, "not_found"
    )
    unread = (await nctx.api.get(f"{V1}/notifications", headers=h, params={"unread": "true"})).json()
    assert unread["unread_count"] == 4 and str(mine[0]) not in [i["id"] for i in unread["items"]]
    read = (await nctx.api.get(f"{V1}/notifications", headers=h, params={"unread": "false"})).json()
    assert [i["id"] for i in read["items"]] == [str(mine[0])] and read["items"][0]["read"] is True

    assert (await nctx.api.post(f"{V1}/notifications/read-all", headers=h)).status_code == 204
    assert (await nctx.api.get(f"{V1}/notifications", headers=h)).json()["unread_count"] == 0
    other = await nctx.as_user(nctx.other)
    assert (await nctx.api.get(f"{V1}/notifications", headers=other)).json()["unread_count"] == 2

    assert_problem(
        await nctx.api.get(f"{V1}/notifications", headers=h, params={"cursor": "bogus"}), 400, "bad_request"
    )
    assert_problem(
        await nctx.api.get(f"{V1}/notifications", headers=h, params={"limit": 0}), 400, "bad_request"
    )
    assert_problem(
        await nctx.api.get(f"{V1}/notifications", headers=h, params={"limit": 201}), 400, "bad_request"
    )
