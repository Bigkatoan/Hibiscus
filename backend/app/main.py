"""FastAPI app factory: ``uvicorn app.main:app`` (or ``create_app(settings)`` in tests).

Middleware order (outermost first): CoreMiddleware (request id, client IP, body limit, security
headers, access log, metrics) -> CORS (only when origins configured) -> routes. Routers of other
packages listed in ``settings.extra_routers`` are mounted when importable (module attribute
``router``, optional ``setup_app(app)`` / ``app_lifespan(app)`` hooks, see :func:`_mount_extra`),
so this file does not need to know the A3/A4/A5 packages.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.router import router as admin_router
from app.auth.cf_access import CfAccessVerifier
from app.auth.jwt import JwtService
from app.auth.passwords import PasswordHasher
from app.auth.router import router as auth_router
from app.auth.turnstile import TurnstileVerifier
from app.auth.users_router import router as users_router
from app.core.clientip import ClientIpResolver
from app.core.crypto import DataCipher
from app.core.db import Database
from app.core.email import create_email_sender
from app.core.errors import install_error_handlers
from app.core.events import configure_events
from app.core.logging import configure_logging
from app.core.middleware import CoreMiddleware
from app.core.ops import router as ops_router
from app.core.pagination import set_cursor_key
from app.core.ratelimit import RateLimiter
from app.core.redis import create_redis
from app.core.services import Services
from app.core.settings import Settings, get_settings
from app.core.storage import S3
from app.workspaces.router import router as workspaces_router

log = logging.getLogger("hibiscus.main")


def build_services(settings: Settings, **overrides: Any) -> Services:
    redis = create_redis(settings.redis_url)
    svc = Services(
        settings=settings,
        db=Database(settings.database_url, pool_size=settings.db_pool_size, null_pool=settings.env == "test"),
        redis=redis,
        s3=S3(settings.s3_endpoint_url, settings.s3_access_key, settings.s3_secret_key, settings.s3_region),
        limiter=RateLimiter(redis, enabled=settings.rate_limit_enabled),
        ip_resolver=ClientIpResolver(settings.trusted_proxy_cidrs),
        cipher=DataCipher(settings.data_key),
        jwt=JwtService(
            settings.jwt_private_key, settings.jwt_previous_public_keys, settings.access_token_ttl_s
        ),
        passwords=PasswordHasher(
            time_cost=settings.argon2_time_cost,
            memory_cost_kib=settings.argon2_memory_cost_kib,
            parallelism=settings.argon2_parallelism,
            breached_file=settings.breached_passwords_file,
        ),
        email=create_email_sender(settings),
        turnstile=TurnstileVerifier(settings.turnstile_secret_key, settings.turnstile_verify_url),
        cf_access=(
            CfAccessVerifier(settings.cf_access_team_domain or "", settings.cf_access_aud or "")
            if settings.cf_access_enabled
            else None
        ),
    )
    return replace(svc, **overrides) if overrides else svc


ExtraLifespan = Callable[[FastAPI], AbstractAsyncContextManager[object]]


def _mount_extra(app: FastAPI, modules: list[str]) -> list[str]:
    """Mount ``router`` of each module; also run its optional hooks.

    * ``setup_app(app)`` is called once at app creation (build package state from
      ``app.state.services`` / ``app.state.settings``).
    * ``app_lifespan(app)`` (async context manager) is entered in the app lifespan, after the core
      services exist and before they are closed (background tasks: reaper, maintenance).
    """
    mounted: list[str] = []
    lifespans: list[ExtraLifespan] = app.state.extra_lifespans
    for name in modules:
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError as e:
            if e.name and name.startswith(e.name):
                continue  # package not merged yet
            raise
        router = getattr(mod, "router", None)
        if isinstance(router, APIRouter):
            app.include_router(router)
            mounted.append(name)
        setup = getattr(mod, "setup_app", None)
        if callable(setup):
            setup(app)
        lifespan = getattr(mod, "app_lifespan", None)
        if callable(lifespan):
            lifespans.append(lifespan)
    return mounted


def create_app(settings: Settings | None = None, **service_overrides: Any) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    svc = build_services(settings, **service_overrides)
    set_cursor_key(settings.cursor_secret)
    configure_events(svc.redis, svc.db)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            for extra in _app.state.extra_lifespans:
                await stack.enter_async_context(extra(_app))
            yield
        await svc.redis.aclose()
        await svc.db.dispose()

    docs = settings.env != "prod"
    app = FastAPI(
        title="Hibiscus API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    app.state.services = svc
    app.state.settings = settings
    app.state.extra_lifespans = []
    install_error_handlers(app)
    for r in (ops_router, auth_router, users_router, workspaces_router, admin_router):
        app.include_router(r)
    app.state.mounted_extra = _mount_extra(app, settings.extra_routers)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=[
                "Content-Type",
                "X-CSRF-Token",
                "X-Request-Id",
                "Idempotency-Key",
                "Authorization",
                "Range",
            ],
            expose_headers=["X-Request-Id", "Retry-After", "Content-Range"],
            max_age=600,
        )
    app.add_middleware(CoreMiddleware, settings=settings, resolver=svc.ip_resolver)
    return app


def __getattr__(name: str) -> Any:
    """Lazy ``app.main:app`` so importing this module never needs production secrets."""
    if name == "app":
        application = create_app()
        globals()["app"] = application
        return application
    raise AttributeError(name)
