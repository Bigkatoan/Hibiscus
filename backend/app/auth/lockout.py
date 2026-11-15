"""Account lockout: after ``threshold`` consecutive failures the account locks for
``base * 2**(failures - threshold)`` seconds (capped). Success resets the counter."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from app.core.errors import ErrorCode, ProblemError
from app.core.settings import Settings
from app.db.models import User


def lock_seconds(failures: int, settings: Settings) -> int:
    if failures < settings.lockout_threshold:
        return 0
    exp = min(failures - settings.lockout_threshold, 30)
    return int(min(settings.lockout_base_s * (2**exp), settings.lockout_max_s))


def ensure_not_locked(user: User, *, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    if user.locked_until is not None and user.locked_until > now:
        retry = max(1, math.ceil((user.locked_until - now).total_seconds()))
        raise ProblemError(423, ErrorCode.ACCOUNT_LOCKED, retry_after_s=retry)


def register_failure(user: User, settings: Settings, *, now: datetime | None = None) -> bool:
    """Increment the failure counter; returns True when this failure (re)locked the account."""
    now = now or datetime.now(UTC)
    user.failed_login_count = min(int(user.failed_login_count) + 1, 32000)
    secs = lock_seconds(user.failed_login_count, settings)
    if secs:
        user.locked_until = now + timedelta(seconds=secs)
        return True
    return False


def register_success(user: User, *, now: datetime | None = None) -> None:
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now or datetime.now(UTC)
