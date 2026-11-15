"""Process-wide service container stored on ``app.state.services`` by the app factory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from redis.asyncio import Redis

from app.core.clientip import ClientIpResolver
from app.core.crypto import DataCipher
from app.core.db import Database
from app.core.ratelimit import RateLimiter
from app.core.settings import Settings
from app.core.storage import S3

if TYPE_CHECKING:
    from app.auth.cf_access import CfAccessVerifier
    from app.auth.jwt import JwtService
    from app.auth.passwords import PasswordHasher
    from app.auth.turnstile import TurnstileVerifier
    from app.core.email import EmailSender


@dataclass
class Services:
    settings: Settings
    db: Database
    redis: Redis
    s3: S3
    limiter: RateLimiter
    ip_resolver: ClientIpResolver
    cipher: DataCipher
    jwt: JwtService
    passwords: PasswordHasher
    email: EmailSender
    turnstile: TurnstileVerifier
    cf_access: CfAccessVerifier | None
