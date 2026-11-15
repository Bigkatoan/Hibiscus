"""Redis client factory (redis-py asyncio)."""

from __future__ import annotations

from typing import cast

from redis.asyncio import Redis


def create_redis(url: str) -> Redis:
    return cast(
        Redis, Redis.from_url(url, decode_responses=False, socket_timeout=5, socket_connect_timeout=5)
    )
