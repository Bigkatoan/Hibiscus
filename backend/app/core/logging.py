"""Structured JSON logging (stdlib) with ``request_id`` / ``run_id`` / ``workspace_id`` and redaction.

Every record gets the current request id and any fields bound with
:func:`app.core.context.bind_log_fields`. Values of sensitive keys (password, token, cookie,
authorization, secret, code ...) are replaced by ``"[REDACTED]"`` in ``extra`` dicts.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.context import log_fields, request_ctx

_SENSITIVE = re.compile(
    r"(pass(word)?|token|secret|cookie|authorization|totp|recovery|otp|api[_-]?key|csrf|set-cookie)", re.I
)
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}
REDACTED = "[REDACTED]"


def redact(value: Any, key: str | None = None) -> Any:
    if key is not None and _SENSITIVE.search(key):
        return REDACTED
    if isinstance(value, dict):
        return {k: redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        ctx = request_ctx.get()
        if ctx.request_id:
            out["request_id"] = ctx.request_id
        out.update(log_fields.get() or {})
        for k, v in record.__dict__.items():
            if k not in _RESERVED and not k.startswith("_"):
                out[k] = redact(v, k)
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).disabled = True
