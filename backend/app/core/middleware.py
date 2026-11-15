"""Pure-ASGI middleware: request id, real client IP, body limit, security headers, access log, metrics."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any

from prometheus_client import Counter, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.clientip import ClientIpResolver
from app.core.context import RequestContext, log_fields, request_ctx
from app.core.errors import instance_of
from app.core.settings import Settings

log = logging.getLogger("hibiscus.access")

_RID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")
_UPLOAD_PART_RE = re.compile(r"^/api/v1/uploads/[^/]+/parts/\d+$")
UPLOAD_PART_MAX = 64 * 1024 * 1024
# Secret-bearing path segments that must never reach the access log (SEC-auth-04). The deprecated
# invite routes still accept the token in the path; deploy/caddy/Caddyfile applies the same filter.
# Matched anywhere and tolerant of duplicate slashes and percent-encoding (N8): `/api/v1//auth/
# invites/<tok>`, `%2F`-encoded separators and `token=` / `token%3D` in any form.
_SEP = r"(?:/|%2F)+"
_SECRET_PATH_RE = re.compile(
    rf"(?i)({_SEP}auth{_SEP}invites{_SEP}|{_SEP}invite{_SEP}|token(?:=|%3D|%253D))[A-Za-z0-9_-]{{32,}}"
)


def redact_path(path: str) -> str:
    return _SECRET_PATH_RE.sub(r"\1REDACTED", path)


REQUESTS = Counter("hibiscus_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram(
    "hibiscus_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1, 2.5, 5, 10),
)

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
DOCS_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; frame-ancestors 'none'"
)


def security_headers(path: str) -> list[tuple[bytes, bytes]]:
    csp = DOCS_CSP if path.startswith(("/api/docs", "/api/redoc")) else API_CSP
    headers = [
        (b"strict-transport-security", b"max-age=63072000; includeSubDomains"),
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
        (b"content-security-policy", csp.encode()),
        (b"cross-origin-opener-policy", b"same-origin"),
        (b"cross-origin-resource-policy", b"same-origin"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    ]
    if (
        path.startswith("/api/v1/auth")
        or path.startswith("/api/v1/admin")
        or path.startswith("/api/v1/users")
    ):
        headers.append((b"cache-control", b"no-store"))
    return headers


class CoreMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings, resolver: ClientIpResolver) -> None:
        self.app = app
        self.settings = settings
        self.resolver = resolver

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        inbound = headers.get("x-request-id", "")
        request_id = inbound if _RID_RE.match(inbound) else uuid.uuid4().hex
        client = scope.get("client")
        peer = str(client[0]) if client else None
        ip = self.resolver.resolve(peer, headers.get("cf-connecting-ip"))
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        state["client_ip"] = ip
        ctx_token = request_ctx.set(
            RequestContext(request_id=request_id, ip=ip, user_agent=headers.get("user-agent"))
        )
        fields_token = log_fields.set(None)
        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET")
        status_holder: dict[str, int] = {"status": 500}

        limit = UPLOAD_PART_MAX if _UPLOAD_PART_RE.match(path) else self.settings.max_body_bytes
        declared = headers.get("content-length")
        try:
            if declared is not None and declared.isdigit() and int(declared) > limit:
                await self._too_large(send, request_id, path, scope)
                status_holder["status"] = 413
                return

            is_upload = limit == UPLOAD_PART_MAX
            if declared is None and method in ("POST", "PUT", "PATCH", "DELETE") and not is_upload:
                # chunked body on a normal endpoint: buffer (≤ 1 MiB) so an oversize body is a clean 413
                chunks: list[bytes] = []
                size = 0
                while True:
                    msg = await receive()
                    if msg["type"] != "http.request":
                        break
                    chunk = msg.get("body", b"")
                    size += len(chunk)
                    if size > limit:
                        await self._too_large(send, request_id, path, scope)
                        status_holder["status"] = 413
                        return
                    chunks.append(chunk)
                    if not msg.get("more_body", False):
                        break
                buffered: list[Message] = [
                    {"type": "http.request", "body": b"".join(chunks), "more_body": False}
                ]
                upstream = receive

                async def replay() -> Message:
                    if buffered:
                        return buffered.pop()
                    return await upstream()

                receive = replay

            received = 0

            async def limited_receive() -> Message:
                nonlocal received
                msg = await receive()
                if msg["type"] == "http.request":
                    received += len(msg.get("body", b""))
                    if received > limit:
                        raise _BodyTooLargeError
                return msg

            started = False

            async def send_wrapper(message: Message) -> None:
                nonlocal started
                if message["type"] == "http.response.start":
                    started = True
                    status_holder["status"] = int(message["status"])
                    hdrs: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                    existing = {k.lower() for k, _ in hdrs}
                    hdrs.append((b"x-request-id", request_id.encode()))
                    for k, v in security_headers(path):
                        if k not in existing:
                            hdrs.append((k, v))
                    message["headers"] = hdrs
                await send(message)

            try:
                await self.app(scope, limited_receive, send_wrapper)
            except _BodyTooLargeError:
                if started:  # pragma: no cover - handlers read the body before responding
                    raise
                await self._too_large(send, request_id, path, scope)
                status_holder["status"] = 413
        finally:
            elapsed = time.perf_counter() - start
            route = _route_template(scope)
            REQUESTS.labels(method, route, str(status_holder["status"])).inc()
            LATENCY.labels(method, route).observe(elapsed)
            if path not in ("/healthz", "/metrics"):
                log.info(
                    "request",
                    extra={
                        "method": method,
                        "path": redact_path(path),
                        "route": route,
                        "status": status_holder["status"],
                        "duration_ms": round(elapsed * 1000, 2),
                        "client_ip": ip,
                    },
                )
            request_ctx.reset(ctx_token)
            log_fields.reset(fields_token)

    async def _too_large(self, send: Send, request_id: str, path: str, scope: Scope) -> None:
        body: dict[str, Any] = {
            "type": f"{self.settings.problem_type_base}payload_too_large",
            "title": "Payload too large",
            "status": 413,
            "code": "payload_too_large",
            "request_id": request_id,
            "instance": instance_of(scope),
        }
        raw = json.dumps(body).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/problem+json"),
                    (b"content-length", str(len(raw)).encode()),
                    (b"x-request-id", request_id.encode()),
                    *security_headers(path),
                ],
            }
        )
        await send({"type": "http.response.body", "body": raw})


class _BodyTooLargeError(Exception):
    pass


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    tmpl = getattr(route, "path", None)
    return str(tmpl) if tmpl else "unmatched"
