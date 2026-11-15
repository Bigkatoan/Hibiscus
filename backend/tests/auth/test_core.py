"""app.core units against real services: email providers, Turnstile, S3/MinIO, events, rate limits,
middleware, logging, settings, pagination, JWT, passwords, client IP, ops endpoints."""

from __future__ import annotations

import asyncio
import base64
import http.server
import json
import logging
import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa
from aiosmtpd.controller import Controller
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import APIRouter, Request

from app.auth.jwt import AccessTokenExpiredError, AccessTokenInvalidError, JwtService
from app.auth.passwords import PasswordHasher, _is_sequence
from app.auth.turnstile import TurnstileVerifier
from app.core import events, pagination
from app.core.clientip import ClientIpResolver
from app.core.crypto import DataCipher
from app.core.email import (
    CloudflareWorkerEmailSender,
    EmailError,
    EmailMessage,
    NoneEmailSender,
    SmtpEmailSender,
    create_email_sender,
    send_safely,
    sign_body,
    verify_signature,
)
from app.core.errors import ErrorCode, ProblemError
from app.core.logging import JsonFormatter, redact
from app.core.ratelimit import RateLimiter
from app.core.settings import Settings, _load_file_secrets
from app.core.storage import BUCKET_UPLOADS, S3
from app.db.models import Run, RunEvent, RunStatus, WorkspaceRole
from tests.auth.fixtures import Ctx, make_settings


# ---------------------------------------------------------------------------------------------
# Tiny real HTTP server (loopback, ephemeral port) used for the email Worker and Turnstile
# ---------------------------------------------------------------------------------------------
class _Recorder(http.server.BaseHTTPRequestHandler):
    queued: ClassVar[list[tuple[int, bytes]]] = []
    received: ClassVar[list[tuple[dict[str, str], bytes]]] = []

    def do_POST(self) -> None:
        n = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(n)
        type(self).received.append(({k.lower(): v for k, v in self.headers.items()}, body))
        status, payload = type(self).queued.pop(0) if type(self).queued else (200, b"{}")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: Any) -> None:
        return


@pytest.fixture
def http_server() -> Iterator[tuple[str, type[_Recorder]]]:
    handler = type("H", (_Recorder,), {"queued": [], "received": []})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    assert srv.server_port not in (8000, 18000)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}", handler
    srv.shutdown()
    srv.server_close()


async def test_cloudflare_worker_sender_signs_requests(http_server: tuple[str, type[_Recorder]]) -> None:
    url, rec = http_server
    sender = CloudflareWorkerEmailSender(
        url + "/send", "s3cret", "Hibiscus <no-reply@example.com>", timeout_s=5
    )
    assert sender.enabled and sender.provider == "cloudflare"
    msg = EmailMessage(to="a@example.com", subject="Hi", text="Body https://x", html="<p>x</p>")
    await sender.send(msg)
    headers, body = rec.received[0]
    data = json.loads(body)
    assert data["to"] == "a@example.com" and data["from"].endswith("<no-reply@example.com>")
    assert data["message_id"] == msg.message_id and data["html"] == "<p>x</p>"
    assert verify_signature("s3cret", headers["x-hibiscus-timestamp"], body, headers["x-hibiscus-signature"])
    assert not verify_signature(
        "other", headers["x-hibiscus-timestamp"], body, headers["x-hibiscus-signature"]
    )
    assert not verify_signature(
        "s3cret", headers["x-hibiscus-timestamp"], body + b" ", headers["x-hibiscus-signature"]
    )
    stale = str(int(time.time()) - 600)
    assert not verify_signature("s3cret", stale, body, sign_body("s3cret", int(stale), body))
    assert not verify_signature("s3cret", "abc", body, "v1=00")
    rec.queued.append((500, b"{}"))
    with pytest.raises(EmailError):
        await sender.send(msg)
    rec.queued.append((401, b"{}"))
    assert await send_safely(sender, msg) is False
    dead = CloudflareWorkerEmailSender("http://127.0.0.1:1/send", "s", "f@example.com", timeout_s=1)
    with pytest.raises(EmailError):
        await dead.send(msg)
    with pytest.raises(ValueError):
        CloudflareWorkerEmailSender("ftp://x", "s", "f")


async def test_smtp_sender_with_real_smtp_server() -> None:
    received: list[Any] = []

    class Handler:
        async def handle_DATA(self, server: Any, session: Any, envelope: Any) -> str:  # noqa: N802 - aiosmtpd API
            received.append(envelope)
            return "250 OK"

    import socket

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    ctl = Controller(Handler(), hostname="127.0.0.1", port=port)
    ctl.start()
    try:
        sender = SmtpEmailSender("127.0.0.1", port, "Hibiscus <no-reply@example.com>", starttls=False)
        await sender.send(EmailMessage(to="b@example.com", subject="Reset", text="plain", html="<b>h</b>"))
        assert received and received[0].rcpt_tos == ["b@example.com"]
        raw = received[0].content.decode()
        assert "Subject: Reset" in raw and "text/html" in raw
        bad = SmtpEmailSender("127.0.0.1", 1, "x@example.com", starttls=False, timeout_s=1)
        with pytest.raises(EmailError):
            await bad.send(EmailMessage(to="b@example.com", subject="s", text="t"))
    finally:
        ctl.stop()


def test_email_factory_and_none_sender() -> None:
    assert isinstance(create_email_sender(make_settings(email_provider="none")), NoneEmailSender)
    s = create_email_sender(make_settings(email_provider="smtp"))
    assert isinstance(s, SmtpEmailSender) and s.enabled
    cf = create_email_sender(
        make_settings(
            email_provider="cloudflare", email_worker_url="https://w.example.com", email_worker_secret="x"
        )
    )
    assert isinstance(cf, CloudflareWorkerEmailSender)
    with pytest.raises(ValueError):
        create_email_sender(make_settings(email_provider="cloudflare"))


async def test_none_sender_outbox_bounded() -> None:
    s = NoneEmailSender()
    for i in range(60):
        await s.send(EmailMessage(to=f"{i}@example.com", subject="s", text="t"))
    assert len(s.outbox) == 50 and s.outbox[-1].to == "59@example.com"
    assert await send_safely(s, EmailMessage(to="x@example.com", subject="s", text="t")) is False


async def test_turnstile(http_server: tuple[str, type[_Recorder]]) -> None:
    url, rec = http_server
    off = TurnstileVerifier(None)
    assert not off.enabled
    await off.verify(None, None)
    on = TurnstileVerifier("secret", url, timeout_s=5)
    with pytest.raises(ProblemError) as e:
        await on.verify(None, "1.2.3.4")
    assert e.value.code == ErrorCode.TURNSTILE_FAILED
    rec.queued.append((200, b'{"success": true}'))
    await on.verify("tok", "1.2.3.4")
    form = rec.received[-1][1].decode()
    assert "secret=secret" in form and "response=tok" in form and "remoteip=1.2.3.4" in form
    rec.queued.append((200, b'{"success": false}'))
    with pytest.raises(ProblemError):
        await on.verify("tok", None)
    rec.queued.append((200, b"not json"))
    with pytest.raises(ProblemError):
        await on.verify("tok", None)
    with pytest.raises(ProblemError):
        await TurnstileVerifier("s", "http://127.0.0.1:1/x", timeout_s=1).verify("tok", None)


async def test_turnstile_enforced_on_login(make_ctx: Any, http_server: tuple[str, type[_Recorder]]) -> None:
    url, rec = http_server
    ctx: Ctx = await make_ctx(turnstile_secret_key="sek", turnstile_site_key="site", turnstile_verify_url=url)
    await ctx.create_user("t@example.com")
    api = ctx.client()
    assert (await api.get("/api/v1/auth/config")).json()["turnstile_site_key"] == "site"
    r = await api.post("/api/v1/auth/login", csrf=False, json={"email": "t@example.com", "password": "x"})
    assert r.status_code == 400 and r.json()["code"] == "turnstile_failed"
    rec.queued.append((200, b'{"success": true}'))
    from tests.auth.fixtures import PASSWORD

    r = await api.post(
        "/api/v1/auth/login",
        csrf=False,
        json={"email": "t@example.com", "password": PASSWORD, "turnstile_token": "ok"},
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------------------------
# Storage (MinIO)
# ---------------------------------------------------------------------------------------------
async def test_s3_multipart_and_range_stream(ctx: Ctx) -> None:
    s3: S3 = ctx.svc.s3
    await s3.ensure_buckets()
    await s3.ensure_buckets()  # idempotent
    await s3.ping()
    key = f"t/{uuid.uuid4()}.bin"
    uid = await s3.create_multipart(BUCKET_UPLOADS, key, "application/octet-stream")
    p1 = b"a" * (5 * 1024 * 1024)
    p2 = b"b" * 1000
    e1 = await s3.put_part(BUCKET_UPLOADS, key, uid, 1, p1)
    e2 = await s3.put_part(BUCKET_UPLOADS, key, uid, 2, p2)
    await s3.complete_multipart(BUCKET_UPLOADS, key, uid, [(2, e2), (1, e1)])
    info = await s3.head_object(BUCKET_UPLOADS, key)
    assert info is not None and info.size == len(p1) + len(p2)
    st = await s3.stream_object(BUCKET_UPLOADS, key, (len(p1) - 2, len(p1) + 1), chunk_size=3)
    assert (st.start, st.end, st.length, st.size) == (len(p1) - 2, len(p1) + 1, 4, len(p1) + len(p2))
    assert b"".join([c async for c in st.body]) == b"aabb"
    tail = await s3.stream_object(BUCKET_UPLOADS, key, (len(p1) + 990, None))
    assert b"".join([c async for c in tail.body]) == b"b" * 10
    with pytest.raises(ProblemError) as e:
        await s3.stream_object(BUCKET_UPLOADS, key, (10**9, None))
    assert e.value.status == 416 and e.value.headers["Content-Range"].startswith("bytes */")
    with pytest.raises(ProblemError) as e:
        await s3.stream_object(BUCKET_UPLOADS, "missing/key")
    assert e.value.status == 404
    assert await s3.head_object(BUCKET_UPLOADS, "missing/key") is None
    await s3.put_object(BUCKET_UPLOADS, "t/empty", b"")
    empty = await s3.stream_object(BUCKET_UPLOADS, "t/empty")
    assert [c async for c in empty.body] == []
    uid2 = await s3.create_multipart(BUCKET_UPLOADS, "t/aborted")
    await s3.abort_multipart(BUCKET_UPLOADS, "t/aborted", uid2)
    await s3.abort_multipart(BUCKET_UPLOADS, "t/aborted", uid2)  # suppressed second time
    assert await s3.bucket_size(BUCKET_UPLOADS) == len(p1) + len(p2)
    assert await s3.delete_prefix(BUCKET_UPLOADS, "t/") == 2
    await s3.delete_object(BUCKET_UPLOADS, key)


# ---------------------------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------------------------
async def _run(ctx: Ctx) -> Run:
    from tests.workspaces.test_workspaces import _make_run

    u = await ctx.create_user(f"ev{uuid.uuid4().hex[:6]}@example.com")
    ws = await ctx.create_workspace(f"ev-{uuid.uuid4().hex[:6]}", {u.id: WorkspaceRole.OWNER})
    rid = await _make_run(ctx, ws.id, u.id, RunStatus.RUNNING)
    async with ctx.session() as s:
        run = await s.get(Run, rid)
        assert run is not None
        return run


async def test_publish_run_event_persist_ephemeral_and_rollback(ctx: Ctx) -> None:
    run = await _run(ctx)
    redis = ctx.svc.redis
    ps = redis.pubsub()
    await ps.subscribe(events.run_channel(run.id), events.workspace_channel(run.workspace_id))
    await ps.get_message(timeout=1)
    await ps.get_message(timeout=1)
    # rolled back => nothing persisted, nothing published
    async with ctx.session() as s:
        await events.publish_run_event(run.id, "metrics", {"kind": "metrics"}, True, db=s)
        await s.rollback()
    assert await ps.get_message(ignore_subscribe_messages=True, timeout=0.5) is None
    # own-session path commits and publishes
    seq = await events.publish_run_event(run.id, "status", {"kind": "status"}, True)
    assert seq == 1
    msgs = []
    for _ in range(2):
        m = await ps.get_message(ignore_subscribe_messages=True, timeout=2)
        assert m is not None
        msgs.append((m["channel"].decode(), json.loads(m["data"])))
    assert (events.run_channel(run.id), {"event": "status", "id": 1, "data": {"kind": "status"}}) in msgs
    assert (
        events.workspace_channel(run.workspace_id),
        {"event": "run.status", "data": {"kind": "status"}},
    ) in msgs
    assert await events.publish_run_event(run.id, "progress", {"step": 5}, False) is None
    m = await ps.get_message(ignore_subscribe_messages=True, timeout=2)
    assert m is not None and json.loads(m["data"]) == {"event": "progress", "data": {"step": 5}}
    await events.publish_workspace_event(run.workspace_id, "model.status", {"id": "x"})
    m = await ps.get_message(ignore_subscribe_messages=True, timeout=2)
    assert m is not None and json.loads(m["data"])["event"] == "model.status"
    rows = await ctx.scalar(sa.select(sa.func.count()).select_from(RunEvent).where(RunEvent.run_id == run.id))
    assert rows == 1
    await ps.aclose()


async def test_events_unconfigured_and_redis_down() -> None:
    saved = (events._state.redis, events._state.db)
    try:
        events.configure_events(None, None)
        with pytest.raises(RuntimeError):
            await events.publish_run_event(uuid.uuid4(), "status", {}, True)
        await events.publish_run_event(uuid.uuid4(), "log", {}, False)  # no redis => silently skipped
        from app.core.redis import create_redis

        events.configure_events(create_redis("redis://127.0.0.1:1/0"), None)
        await events.publish_run_event(uuid.uuid4(), "log", {}, False)  # logged, not raised
    finally:
        events.configure_events(*saved)


# ---------------------------------------------------------------------------------------------
# Rate limits / middleware / errors
# ---------------------------------------------------------------------------------------------
async def test_login_rate_limit_per_email(ctx: Ctx) -> None:
    api = ctx.client()
    codes = []
    for i in range(ctx.settings.rl_login_email_per_min + 1):
        r = await api.post(
            "/api/v1/auth/login", csrf=False, json={"email": "rl@example.com", "password": f"x{i}"}
        )
        codes.append(r.status_code)
    assert codes[-1] == 429 and set(codes[:-1]) == {401}
    last = r.json()
    assert last["code"] == "rate_limited" and int(r.headers["retry-after"]) >= 1


async def test_rate_limiter_fail_open_and_reset() -> None:
    from app.core.redis import create_redis

    down = RateLimiter(create_redis("redis://127.0.0.1:1/0"))
    for _ in range(5):
        await down.hit("b", "id", limit=1, window_s=60)
    off = RateLimiter(create_redis("redis://127.0.0.1:1/0"), enabled=False)
    await off.hit("b", "id", limit=0, window_s=60)
    await down.hit("b", None, limit=0, window_s=60)


async def test_rate_limiter_real_redis(ctx: Ctx) -> None:
    rl = RateLimiter(ctx.svc.redis)
    await rl.hit("unit", "k", limit=2, window_s=60)
    await rl.hit("unit", "k", limit=2, window_s=60)
    with pytest.raises(ProblemError) as e:
        await rl.hit("unit", "k", limit=2, window_s=60)
    assert e.value.status == 429 and e.value.headers["Retry-After"]
    await rl.reset("unit", "k", window_s=60)
    await rl.hit("unit", "k", limit=2, window_s=60)
    keys = [k.decode() for k in await ctx.svc.redis.keys("hibiscus:rl:unit:*")]
    assert keys and all("k" not in k.split(":")[3] or len(k.split(":")[3]) == 32 for k in keys)


async def test_request_id_body_limit_and_problem_handlers(ctx: Ctx) -> None:
    api = ctx.client(validate=False)
    r = await api.get("/healthz", headers={"X-Request-Id": "abcdef12-req"})
    assert r.headers["x-request-id"] == "abcdef12-req"
    r = await api.get("/healthz", headers={"X-Request-Id": "bad id with spaces"})
    assert r.headers["x-request-id"] != "bad id with spaces" and len(r.headers["x-request-id"]) == 32
    big = b"{" + b" " * (1024 * 1024 + 10) + b"}"
    r = await api.http.post("/api/v1/auth/login", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["code"] == "payload_too_large"

    async def chunks() -> Any:
        for _ in range(3):
            yield b" " * (600 * 1024)

    r = await api.http.post(
        "/api/v1/auth/login", content=chunks(), headers={"content-type": "application/json"}
    )
    assert r.status_code == 413
    r = await api.get("/api/v1/does-not-exist")
    assert (
        r.status_code == 404
        and r.json()["code"] == "not_found"
        and r.headers["content-type"].startswith("application/problem+json")
    )
    r = await api.http.put("/api/v1/auth/login")
    assert r.status_code == 405 and r.json()["code"] == "bad_request"

    from fastapi import APIRouter

    boom = APIRouter()

    @boom.get("/api/v1/boom")
    async def _boom() -> None:
        raise RuntimeError("kaboom secret=xyz")

    ctx.app.include_router(boom)
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=ctx.app, raise_app_exceptions=False), base_url="https://testserver"
    ) as c:
        r = await c.get("/api/v1/boom")
    assert r.status_code == 500 and r.json()["code"] == "internal_error" and "kaboom" not in r.text


async def test_upload_part_path_allows_64mib_and_streams_limit(ctx: Ctx) -> None:
    r = APIRouter()

    @r.put("/api/v1/uploads/{upload_id}/parts/{n}")
    async def part(upload_id: str, n: int, request: Request) -> dict[str, int]:
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
        return {"bytes": total}

    ctx.app.include_router(r)
    api = ctx.client(validate=False)
    two_mib = b"x" * (2 * 1024 * 1024)
    ok = await api.http.put("/api/v1/uploads/u/parts/1", content=two_mib)
    assert ok.status_code == 200 and ok.json() == {"bytes": len(two_mib)}
    declared = await api.http.put(
        "/api/v1/uploads/u/parts/1", content=b"x", headers={"content-length": str(64 * 1024 * 1024 + 1)}
    )
    assert declared.status_code == 413

    async def body() -> Any:
        for _ in range(65):
            yield b"y" * (1024 * 1024)

    streamed = await api.http.put("/api/v1/uploads/u/parts/2", content=body())
    assert streamed.status_code == 413 and streamed.json()["code"] == "payload_too_large"


async def test_cors_only_when_configured(make_ctx: Any) -> None:
    ctx: Ctx = await make_ctx(cors_origins=["http://localhost:5173"])
    api = ctx.client(validate=False)
    r = await api.http.options(
        "/api/v1/auth/login",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert r.headers["access-control-allow-credentials"] == "true"
    r = await api.http.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in r.headers


async def test_readyz_and_metrics(ctx: Ctx) -> None:
    api = ctx.client()
    r = await api.get("/readyz")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready" and set(body["checks"]) == {"postgres", "redis", "minio"}
    assert "no alembic_version" in body["checks"]["postgres"]["detail"]
    async with ctx.session() as s:
        await s.execute(sa.text("CREATE TABLE IF NOT EXISTS alembic_version (version_num varchar(32))"))
        await s.execute(sa.text("INSERT INTO alembic_version VALUES ('0001_initial')"))
        await s.commit()
    try:
        assert "0001_initial" in (await api.get("/readyz")).json()["checks"]["postgres"]["detail"]
    finally:
        async with ctx.session() as s:
            await s.execute(sa.text("DROP TABLE alembic_version"))
            await s.commit()
    r = await api.get("/metrics")
    assert r.status_code == 200 and "hibiscus_http_requests_total" in r.text


async def test_readyz_not_ready(make_ctx: Any) -> None:
    ctx: Ctx = await make_ctx(redis_url="redis://127.0.0.1:1/0", s3_endpoint_url="http://127.0.0.1:1")
    r = await ctx.client().get("/readyz")
    assert r.status_code == 503 and r.json()["status"] == "not_ready"
    assert r.json()["checks"]["redis"]["ok"] is False and r.json()["checks"]["postgres"]["ok"] is True


async def test_app_mounts_extra_routers(make_ctx: Any) -> None:
    # a package that does not exist is skipped; a module without `router` is skipped
    ctx: Ctx = await make_ctx(extra_routers=["app.not_a_package.router", "app.core.ops", "app.db"])
    assert ctx.app.state.mounted_extra == ["app.core.ops"]
    # a router module that exists but fails to import (missing dependency) must not be skipped
    with pytest.raises(ModuleNotFoundError):
        await make_ctx(extra_routers=["tests.auth._broken_router"])


# ---------------------------------------------------------------------------------------------
# Logging, settings, pagination, crypto, JWT, passwords, IP
# ---------------------------------------------------------------------------------------------
def test_json_logging_redacts_and_carries_request_id() -> None:
    from app.core.context import RequestContext, bind_log_fields, log_fields, request_ctx

    tok = request_ctx.set(RequestContext(request_id="rid-123"))
    ftok = log_fields.set(None)
    try:
        bind_log_fields(run_id="r1")
        bind_log_fields(workspace_id="w1")
        rec = logging.LogRecord("x", logging.INFO, __file__, 1, "hello %s", ("world",), None)
        rec.password = "hunter2"
        rec.details = {"token": "abc", "nested": {"Authorization": "Bearer x"}, "ok": [1, {"secret": 2}]}
        out = json.loads(JsonFormatter().format(rec))
        assert out["msg"] == "hello world" and out["request_id"] == "rid-123"
        assert out["run_id"] == "r1" and out["workspace_id"] == "w1"
        assert out["password"] == "[REDACTED]" and out["details"]["token"] == "[REDACTED]"
        assert (
            out["details"]["nested"]["Authorization"] == "[REDACTED]"
            and out["details"]["ok"][1]["secret"] == "[REDACTED]"
        )
        try:
            raise ValueError("x")
        except ValueError:
            import sys

            rec2 = logging.LogRecord("x", logging.ERROR, __file__, 1, "err", (), sys.exc_info())
        assert "ValueError" in json.loads(JsonFormatter().format(rec2))["exc"]
    finally:
        request_ctx.reset(tok)
        log_fields.reset(ftok)
    assert redact({"a": 1}) == {"a": 1}
    from app.core.logging import configure_logging

    configure_logging("INFO", json_output=False)
    configure_logging("WARNING", json_output=True)


def test_settings_prod_validation_and_file_secrets(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="missing required secrets"):
        Settings(env="prod", jwt_private_key="", data_key="", cursor_secret="")
    key = (
        Ed25519PrivateKey.generate()
        .private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        .decode()
    )
    dk = base64.b64encode(b"k" * 32).decode()
    ok = Settings(env="prod", jwt_private_key=key, data_key=dk, cursor_secret="c")
    assert ok.email_delivery_enabled is False and ok.cf_access_enabled is False
    with pytest.raises(ValueError, match="cloudflare"):
        Settings(env="prod", jwt_private_key=key, data_key=dk, cursor_secret="c", email_provider="cloudflare")
    with pytest.raises(ValueError, match="32 bytes"):
        Settings(env="dev", data_key=base64.b64encode(b"short").decode())
    with pytest.raises(ValueError):
        Settings(env="dev", trusted_proxy_cidrs=["not-a-cidr"])
    secret_file = tmp_path / "cursor"
    secret_file.write_text("from-file\n")
    monkeypatch.setenv("HIBISCUS_CURSOR_SECRET_FILE", str(secret_file))
    monkeypatch.delenv("HIBISCUS_CURSOR_SECRET", raising=False)
    _load_file_secrets()
    import os

    assert os.environ["HIBISCUS_CURSOR_SECRET"] == "from-file"
    monkeypatch.delenv("HIBISCUS_CURSOR_SECRET")
    s = Settings(env="dev")
    assert s.link("/x#token={token}", "abc") == "https://robot.example.com/x#token=abc"
    from app.core.settings import get_settings, settings_from

    get_settings.cache_clear()
    monkeypatch.setenv("HIBISCUS_ENV", "dev")
    assert get_settings().env == "dev"
    assert settings_from(env="test").env == "test"
    get_settings.cache_clear()


def test_pagination_cursor_roundtrip_and_tamper() -> None:
    pagination.set_cursor_key("k1")
    c = pagination.encode_cursor({"id": 5, "ts": "2026"})
    assert pagination.decode_cursor(c) == {"id": 5, "ts": "2026"}
    for bad in (
        c[:-2] + "AA",
        "nodot",
        "!!!.###",
        c.split(".")[0] + ".",
        pagination.encode_cursor({"x": 1}) + "x",
    ):
        with pytest.raises(ProblemError):
            pagination.decode_cursor(bad)
    pagination.set_cursor_key(b"k2")
    with pytest.raises(ProblemError):
        pagination.decode_cursor(c)
    import hashlib
    import hmac

    payload = b"[1,2]"
    sig = hmac.new(b"k2", payload, hashlib.sha256).digest()[:16]
    arr = (
        base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
        + "."
        + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    )
    with pytest.raises(ProblemError):
        pagination.decode_cursor(arr)


def test_data_cipher_and_aad() -> None:
    c = DataCipher(base64.b64encode(b"x" * 32).decode())
    blob = c.encrypt(b"secret", b"ctx")
    assert c.decrypt(blob, b"ctx") == b"secret"
    with pytest.raises(Exception):  # noqa: B017 - InvalidTag
        c.decrypt(blob, b"other")
    with pytest.raises(ValueError):
        DataCipher(base64.b64encode(b"short").decode())


def test_jwt_issue_decode_rotation_and_errors() -> None:
    def pem(k: Ed25519PrivateKey) -> str:
        return k.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode()

    old, new = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    old_pub = (
        old.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    svc_old = JwtService(pem(old))
    svc_new = JwtService(pem(new), [old_pub], ttl_s=900)
    uid, sid = uuid.uuid4(), uuid.uuid4()
    claims = svc_new.decode(svc_old.issue(uid, sid, True))  # previous key still accepted
    assert claims.user_id == uid and claims.session_id == sid and claims.mfa is True
    assert claims.expires_at - claims.issued_at == 900
    with pytest.raises(AccessTokenInvalidError):
        svc_old.decode(svc_new.issue(uid, sid, False))
    with pytest.raises(AccessTokenExpiredError):
        svc_new.decode(svc_new.issue(uid, sid, False, now=int(time.time()) - 2000))
    assert (
        svc_new.decode(svc_new.issue(uid, sid, False, now=int(time.time()) - 2000), verify_exp=False).user_id
        == uid
    )
    import jwt as pyjwt

    hs = pyjwt.encode(
        {"sub": str(uid), "sid": str(sid), "iat": 1, "exp": 2**31, "iss": "hibiscus", "aud": "hibiscus-api"},
        "k" * 32,
        algorithm="HS256",
    )
    with pytest.raises(AccessTokenInvalidError):
        svc_new.decode(hs)
    from cryptography.hazmat.primitives.asymmetric import ec

    ec_pem = (
        ec.generate_private_key(ec.SECP256R1())
        .private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        .decode()
    )
    with pytest.raises(ValueError):
        JwtService(ec_pem)
    ec_pub = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    with pytest.raises(ValueError):
        JwtService(pem(new), [ec_pub])


def test_password_hasher_policy_and_breached_file(tmp_path: Any) -> None:
    import hashlib

    f = tmp_path / "hibp.txt"
    f.write_text(
        "# comment\n\n"
        + hashlib.sha1(b"Unique-Leaked-Phrase-99", usedforsecurity=False).hexdigest().upper()
        + ":42\n"
        + "plain-leaked-password-x\n"
    )
    ph = PasswordHasher(time_cost=1, memory_cost_kib=8, parallelism=1, breached_file=str(f))
    PasswordHasher(time_cost=1, memory_cost_kib=8, parallelism=1, breached_file=str(tmp_path / "missing.txt"))
    h = ph.hash("Some-Password-123")
    assert ph.verify(h, "Some-Password-123") and not ph.verify(h, "nope")
    assert not ph.verify("not-a-hash", "x")
    assert not ph.needs_rehash(h) and ph.needs_rehash("garbage")
    assert PasswordHasher(time_cost=2, memory_cost_kib=16, parallelism=1).needs_rehash(h)
    ph.dummy_verify("x")
    assert ph.is_breached("Unique-Leaked-Phrase-99") and ph.is_breached("plain-leaked-password-x")
    assert ph.is_breached("qwertyuiopasdfgh")  # built-in seed list
    ph.check_policy("Fine-Unusual-Passphrase-7", email="joe@example.com", display_name="Joe")
    for weak in ("abcdefghijkl", "123456789012", "aaaaaaaaaaaab", "short", "joejoejoe12345"[:12]):
        with pytest.raises(ProblemError) as e:
            ph.check_policy(weak, email="joe@example.com", display_name="Joe")
        assert e.value.code == ErrorCode.PASSWORD_TOO_WEAK
    with pytest.raises(ProblemError) as e:
        ph.check_policy("Unique-Leaked-Phrase-99")
    assert e.value.code == ErrorCode.PASSWORD_BREACHED
    assert _is_sequence("9876543210") and not _is_sequence("a") and not _is_sequence("ab1")


def test_client_ip_resolver() -> None:
    r = ClientIpResolver(["172.18.0.0/16", "::1/128"])
    assert r.resolve("172.18.0.5", "203.0.113.9") == "203.0.113.9"
    assert r.resolve("::1", "2001:db8::1") == "2001:db8::1"
    assert r.resolve("10.0.0.1", "203.0.113.9") == "10.0.0.1"  # untrusted peer: header ignored
    assert r.resolve("172.18.0.5", "not-an-ip") == "172.18.0.5"
    assert r.resolve("172.18.0.5", None) == "172.18.0.5"
    assert r.resolve(None, "203.0.113.9") is None
    assert r.resolve("garbage", "203.0.113.9") is None
    assert not r.is_trusted("garbage") and not r.is_trusted(None)


async def test_cf_access_http_fetch_failure_is_forbidden() -> None:
    from app.auth.cf_access import CfAccessVerifier

    v = CfAccessVerifier("127.0.0.1:1", "aud")
    import jwt as pyjwt

    tok = pyjwt.encode({"a": 1}, "k" * 32, algorithm="HS256", headers={"kid": "x"})
    with pytest.raises(ProblemError):
        await v.verify_token(tok)

    async def bad_keys() -> dict[str, Any]:
        return {"keys": [{"kty": "nope", "kid": "x"}]}

    v2 = CfAccessVerifier("team.example.com", "aud", fetch_jwks=bad_keys)
    with pytest.raises(ProblemError):
        await v2.verify_token(tok)
    _ = asyncio
