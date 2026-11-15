"""Ops endpoints at the root (not under /api/v1): /healthz (public), /readyz and /metrics (internal)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import inspect, text
from starlette.responses import JSONResponse, Response

from app.core.deps import services

router = APIRouter(tags=["ops"])


@router.get("/healthz", operation_id="healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


async def _timed(fn: Callable[[], Awaitable[str | None]]) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        detail = await asyncio.wait_for(fn(), timeout=3.0)
        out: dict[str, Any] = {"ok": True, "latency_ms": round((time.perf_counter() - t0) * 1000, 2)}
        if detail:
            out["detail"] = detail
        return out
    except Exception as e:
        return {
            "ok": False,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "detail": type(e).__name__,
        }


@router.get("/readyz", operation_id="readyz")
async def readyz(request: Request) -> JSONResponse:
    svc = services(request)

    async def pg() -> str | None:
        async with svc.db.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            has_alembic = await conn.run_sync(lambda c: inspect(c).has_table("alembic_version"))
            if not has_alembic:
                return "no alembic_version table (schema not managed by migrations)"
            rev = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
            return f"migration {rev}"

    async def redis() -> str | None:
        await svc.redis.ping()
        return None

    async def s3() -> str | None:
        await svc.s3.ping()
        return None

    checks = dict(
        zip(
            ("postgres", "redis", "minio"),
            await asyncio.gather(_timed(pg), _timed(redis), _timed(s3)),
            strict=True,
        )
    )
    ok = all(c["ok"] for c in checks.values())
    return JSONResponse(
        {"status": "ready" if ok else "not_ready", "checks": checks}, status_code=200 if ok else 503
    )


@router.get("/metrics", operation_id="prometheusMetrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
