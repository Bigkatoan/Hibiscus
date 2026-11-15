"""Mount point for the datasets slice (``settings.extra_routers`` entry ``app.datasets.router``).

* ``router`` — datasets, dataset-versions and uploads under ``/api/v1``.
* ``setup_app(app)`` — builds :class:`DatasetStorage` from the core settings.
* ``app_lifespan(app)`` — hourly maintenance: :func:`expire_stale_uploads` (docs/db-schema.md
  "Retention").
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, FastAPI

from app.core.services import Services
from app.datasets import api_datasets, api_uploads
from app.datasets.storage import DatasetStorage

log = logging.getLogger("hibiscus.datasets")
MAINTENANCE_INTERVAL_S = 3600.0

router = APIRouter(prefix="/api/v1")
router.include_router(api_datasets.router)
router.include_router(api_uploads.router)


def setup_app(app: FastAPI) -> None:
    svc: Services = app.state.services
    app.state.datasets_storage = DatasetStorage.from_settings(svc.settings)


async def _maintenance_loop(app: FastAPI, interval_s: float) -> None:
    svc: Services = app.state.services
    storage: DatasetStorage = app.state.datasets_storage
    while True:
        try:
            async with svc.db.sessionmaker() as db:
                n = await api_uploads.expire_stale_uploads(db, storage)
            if n:
                log.info("expired stale uploads", extra={"count": n})
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("upload maintenance failed")
        await asyncio.sleep(interval_s)


@contextlib.asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_maintenance_loop(app, MAINTENANCE_INTERVAL_S))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


__all__ = ["app_lifespan", "router", "setup_app"]
