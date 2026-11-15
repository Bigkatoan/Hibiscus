"""Synchronous Postgres access for workers (SQLAlchemy Core + psycopg 3).

Workers do not import the API package; they use bound-parameter ``text()`` statements against the
frozen schema (``backend/app/db/models.py``). Integration tests create the schema from those
models, so every statement here is checked against the real contract.

Public API (stable for A3/A5):
    * :func:`make_engine`
    * :func:`with_retry` - retry transient DB errors with backoff for up to ``db_retry_budget_s``
      (run-lifecycle §8: Postgres restart must not kill a running training process).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import DBAPIError, OperationalError

log = logging.getLogger(__name__)
T = TypeVar("T")


def make_engine(url: str, *, pool_size: int = 4) -> Engine:
    return create_engine(url, pool_size=pool_size, max_overflow=2, pool_pre_ping=True, future=True)


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, OperationalError):
        return True
    return isinstance(exc, DBAPIError) and bool(exc.connection_invalidated)


def with_retry[T](fn: Callable[[], T], *, budget_s: float = 50.0, what: str = "db") -> T:
    """Call ``fn`` and retry on connection-level errors (exponential backoff, 0.5 s .. 8 s)."""
    deadline = time.monotonic() + budget_s
    delay = 0.5
    while True:
        try:
            return fn()
        except Exception as exc:
            if not _is_transient(exc) or time.monotonic() + delay > deadline:
                raise
            log.warning("transient %s error, retrying in %.1fs: %s", what, delay, type(exc).__name__)
            time.sleep(delay)
            delay = min(delay * 2, 8.0)
