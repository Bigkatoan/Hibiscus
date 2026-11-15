"""Redis fixed-window rate limiter.

``await limiter.hit("login:ip", ip, limit=20, window_s=60)`` raises ``ProblemError(429,
rate_limited, retry_after_s=...)`` once ``limit`` is exceeded within the window. Redis errors
fail **open** (logged): account lockout in Postgres still protects credentials.
"""

from __future__ import annotations

import hashlib
import logging
import time

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import ErrorCode, ProblemError

log = logging.getLogger("hibiscus.ratelimit")


class RateLimiter:
    def __init__(self, redis: Redis, *, enabled: bool = True, prefix: str = "hibiscus:rl") -> None:
        self._redis = redis
        self.enabled = enabled
        self._prefix = prefix

    def _key(self, bucket: str, ident: str, window_s: int, now: float) -> tuple[str, int]:
        window = int(now // window_s)
        digest = hashlib.sha256(ident.encode()).hexdigest()[:32]  # never store raw emails / IPs as keys
        reset_in = int((window + 1) * window_s - now) + 1
        return f"{self._prefix}:{bucket}:{digest}:{window}", reset_in

    async def hit(self, bucket: str, ident: str | None, *, limit: int, window_s: int) -> None:
        if not self.enabled or not ident:
            return
        key, reset_in = self._key(bucket, ident, window_s, time.time())
        try:
            pipe = self._redis.pipeline(transaction=True)
            pipe.incr(key)
            pipe.expire(key, window_s + 1)
            count, _ = await pipe.execute()
        except (RedisError, OSError):
            log.warning("rate limiter unavailable; failing open", extra={"bucket": bucket})
            return
        if int(count) > limit:
            raise ProblemError(429, ErrorCode.RATE_LIMITED, retry_after_s=max(1, reset_in))

    async def reset(self, bucket: str, ident: str, *, window_s: int) -> None:
        key, _ = self._key(bucket, ident, window_s, time.time())
        try:
            await self._redis.delete(key)
        except (RedisError, OSError):  # pragma: no cover - best effort
            pass
