"""Stand-in for the real API (A2/A3/A4), used ONLY by deploy/tests/test_stack_smoke.py to exercise
the reverse proxy, image build, healthchecks and Prometheus scraping before the real app exists.
It is built with the production deploy/docker/api.Dockerfile."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

app = FastAPI()
REQUESTS = Counter("hibiscus_http_requests_total", "requests", ["method", "route", "status"])
LATENCY = Histogram("hibiscus_http_request_duration_seconds", "latency", ["method", "route"])


@app.middleware("http")
async def metrics(request: Request, call_next):  # type: ignore[no-untyped-def]
    start = time.perf_counter()
    response = await call_next(request)
    route = request.url.path
    REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    LATENCY.labels(request.method, route).observe(time.perf_counter() - start)
    return response


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, object]:
    return {"status": "ready", "checks": {}}


@app.get("/metrics")
async def prom() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.api_route("/api/v1/stub/echo", methods=["GET", "POST"])
async def echo(request: Request) -> JSONResponse:
    body = await request.body()
    return JSONResponse(
        {
            "client": request.client.host if request.client else None,
            "x_forwarded_for": request.headers.get("x-forwarded-for"),
            "x_real_ip": request.headers.get("x-real-ip"),
            "cf_connecting_ip": request.headers.get("cf-connecting-ip"),
            "body_bytes": len(body),
        }
    )


@app.put("/api/v1/uploads/{upload_id}/parts/{part}")
async def part(upload_id: str, part: int, request: Request) -> dict[str, int]:
    n = 0
    async for chunk in request.stream():
        n += len(chunk)
    return {"part": part, "bytes": n}


@app.get("/api/v1/stub/sse")
async def sse() -> StreamingResponse:
    async def events() -> AsyncIterator[bytes]:
        for i in range(3):
            yield f"event: tick\ndata: {i} {time.time()}\n\n".encode()
            await asyncio.sleep(1.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/v1/stub/text")
async def text() -> PlainTextResponse:
    return PlainTextResponse("ok")
