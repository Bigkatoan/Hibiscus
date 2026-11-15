"""Fixtures: real PG/Redis/MinIO app with only the notifications slice + a local HTTPS receiver."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from app.main import create_app
from app.notifications.router import NotificationsState, setup_app
from app.notifications.settings import NotificationSettings
from tests.auth.fixtures import Api, Infra, containers, make_settings, reset_db  # noqa: F401
from tests.integration.authn import create_user, session_headers
from tests.notifications.helpers import HOOK_HOST, TEST_DNS, HookServer, fake_dns, make_tls


@pytest.fixture(scope="session")
def tls(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, Path]:
    return make_tls(tmp_path_factory.mktemp("tls"))


@pytest.fixture
def hook(tls: tuple[Path, Path, Path]) -> Iterator[HookServer]:
    ca, leaf, key = tls
    srv = HookServer(ca=ca).start(leaf, key)
    try:
        yield srv
    finally:
        srv.stop()


def notify_settings(hook: HookServer, **over: Any) -> NotificationSettings:
    base: dict[str, Any] = {
        "dispatcher_enabled": False,
        "ssrf_allow_cidrs": ["127.0.0.1/32"],
        "ca_file": str(hook.ca),
        "discord_hosts": ["discord.com", HOOK_HOST],
        "telegram_api_base": f"https://{HOOK_HOST}:{hook.port}/tg",
        "backoff_base_s": 0.0,
        "connect_timeout_s": 2.0,
        "timeout_s": 3.0,
    }
    base.update(over)
    return NotificationSettings(**base)


@dataclass
class NCtx:
    app: Any
    api: Api
    state: NotificationsState
    user: uuid.UUID
    other: uuid.UUID
    hook: HookServer

    async def as_user(self, uid: uuid.UUID | None = None) -> dict[str, str]:
        return await session_headers(self.app, uid or self.user)


async def build(infra_: Infra, hook: HookServer, settings_over: dict[str, Any], **svc: Any) -> NCtx:
    await reset_db(infra_.pg_url)
    app = create_app(make_settings(extra_routers=["app.notifications.router"]), **svc)
    await app.state.services.redis.flushdb()
    state = setup_app(app, notify_settings(hook, **settings_over), resolver=fake_dns(TEST_DNS))
    user = await create_user(app, email="owner@example.com")
    other = await create_user(app, email="other@example.com")
    return NCtx(app, Api(app), state, user, other, hook)


@pytest.fixture
async def nctx(containers: Infra, hook: HookServer) -> AsyncIterator[NCtx]:  # noqa: F811
    c = await build(containers, hook, {})
    try:
        yield c
    finally:
        await c.api.aclose()
        await c.app.state.services.redis.aclose()
        await c.app.state.services.db.dispose()
