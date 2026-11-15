"""Per-request context (contextvars) used by logging and audit."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str | None = None
    ip: str | None = None
    user_agent: str | None = None


request_ctx: ContextVar[RequestContext] = ContextVar("hibiscus_request_ctx", default=RequestContext())  # noqa: B039 - frozen dataclass
log_fields: ContextVar[dict[str, str] | None] = ContextVar("hibiscus_log_fields", default=None)


def bind_log_fields(**fields: str) -> None:
    """Attach fields (``run_id``, ``workspace_id``, ``user_id``) to every later log line of this task."""
    current = dict(log_fields.get() or {})
    current.update(fields)
    log_fields.set(current)
