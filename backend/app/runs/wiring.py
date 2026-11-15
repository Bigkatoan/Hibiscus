"""Mount the runs/models domain into the app (``settings.extra_routers`` entry ``app.runs.wiring``).

* ``router`` — policies, runs (+ SSE, logs, metrics), gpus/queue, jobs, models and
  ``PATCH /admin/gpus/{gpu_id}``, all under ``/api/v1``.
* ``setup_app(app)`` — ``app.state.runs`` (:class:`RunsState`) built from the core services: the
  one engine/sessionmaker and Redis client of ``app.state.services`` plus an artifact store.
* ``app_lifespan(app)`` — starts/stops the leader-elected lease reaper.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import redis.asyncio as aioredis
from fastapi import APIRouter, FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.services import Services
from app.models.router import router as models_router
from app.runs.admin_gpus import router as admin_gpus_router
from app.runs.gpus import router as gpus_router
from app.runs.jobs import router as jobs_router
from app.runs.observe import router as observe_router
from app.runs.policies import router as policies_router
from app.runs.router import router as runs_router
from app.runs.settings import RunsSettings, get_runs_settings
from app.runs.storage import AsyncStore
from app.runs.stream import router as stream_router


@dataclass
class RunsState:
    settings: RunsSettings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    redis: aioredis.Redis | None
    store: AsyncStore
    tasks: list[asyncio.Task[None]] = field(default_factory=list)


router = APIRouter(prefix="/api/v1")
for _r in (
    policies_router,
    runs_router,
    observe_router,
    stream_router,
    gpus_router,
    jobs_router,
    admin_gpus_router,
    models_router,
):
    router.include_router(_r)


def setup_app(app: FastAPI, settings: RunsSettings | None = None) -> RunsState:
    svc: Services = app.state.services
    state = RunsState(
        settings=settings or get_runs_settings(),
        engine=svc.db.engine,
        sessionmaker=svc.db.sessionmaker,
        redis=svc.redis,
        store=AsyncStore.from_settings(svc.settings),
    )
    app.state.runs = state
    return state


@contextlib.asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[RunsState]:
    """Start the reaper (if ``run_reaper``). Engine/Redis are owned and closed by the core lifespan."""
    state: RunsState = app.state.runs
    s = state.settings
    if s.run_reaper:
        from app.runs.reaper import reaper_loop

        state.tasks.append(
            asyncio.create_task(
                reaper_loop(state.engine, state.sessionmaker, state.redis, s.reaper_interval_s)
            )
        )
    try:
        yield state
    finally:
        for t in state.tasks:
            t.cancel()
        for t in state.tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        state.tasks.clear()
