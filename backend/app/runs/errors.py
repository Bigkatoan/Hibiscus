"""Run-domain shortcuts for :class:`app.core.errors.ProblemError` (the one problem+json class).

The handler is installed by ``app.main.create_app``; this module only builds common errors.
"""

from __future__ import annotations

from app.core.errors import ErrorCode, ProblemError

__all__ = ["ErrorCode", "ProblemError", "invalid_transition", "not_found"]


def not_found(detail: str = "Not found") -> ProblemError:
    return ProblemError(404, ErrorCode.NOT_FOUND, detail)


def invalid_transition(status: str, action: str) -> ProblemError:
    return ProblemError(
        409,
        ErrorCode.RUN_INVALID_TRANSITION,
        f"cannot {action} a run in status {status}",
        params={"status": status},
    )
