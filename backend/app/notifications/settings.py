"""Notification-domain settings (env ``HIBISCUS_NOTIFY_*``), separate from ``app.core.settings``."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class NotificationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HIBISCUS_NOTIFY_", extra="ignore")

    #: Start the leader-elected delivery loop in the API lifespan.
    dispatcher_enabled: bool = True
    poll_interval_s: float = 2.0
    batch_size: int = 50
    #: Concurrent outbound requests per iteration.
    concurrency: int = 5
    max_attempts: int = 5
    #: Backoff after attempt n (1-based): ``min(backoff_base_s * 4**(n-1), backoff_max_s)``.
    backoff_base_s: float = 30.0
    backoff_max_s: float = 3600.0
    #: A claimed delivery is invisible to other dispatchers for this long (crash safety).
    claim_ttl_s: float = 120.0
    #: Notifications older than this when first seen are not sent externally (no replay storms).
    max_age_s: float = 86400.0

    connect_timeout_s: float = 5.0
    timeout_s: float = 10.0
    max_response_bytes: int = 64 * 1024

    max_channels_per_user: int = 10
    test_rate_per_min: int = 5
    test_rate_per_hour: int = 30

    discord_hosts: list[str] = Field(
        default_factory=lambda: ["discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com"]
    )
    telegram_api_base: str = "https://api.telegram.org"

    #: DANGEROUS, tests/dev only: networks exempt from the SSRF block list. Refused when env=prod.
    ssrf_allow_cidrs: list[str] = Field(default_factory=list)
    #: Extra CA bundle (PEM) trusted for outbound HTTPS in addition to the system store (tests).
    ca_file: str | None = None


@lru_cache(maxsize=1)
def get_notification_settings() -> NotificationSettings:
    return NotificationSettings()
