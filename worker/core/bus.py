"""Redis pub/sub channel names and envelopes (run-lifecycle §9). Shared by API and workers.

Channels
    * ``hibiscus:run:<run_id>``        - every run event (persisted ones carry ``id`` = seq)
    * ``hibiscus:ws:<workspace_id>``   - workspace stream (``run.status``, ``job.status``, ...)
    * ``hibiscus:queue``               - wake-up hint for workers when something was enqueued
    * ``hibiscus:control:<gpu_id>``    - desired_state change hint for the worker holding ``gpu_id``

Envelope on ``hibiscus:run:*``: ``{"event": "<type>", "id": <seq or null>, "data": {...}}``.
Envelope on ``hibiscus:ws:*``: ``{"event": "run.status", "data": {...}}``.

Redis is best effort: a failed publish is logged and swallowed (persisted events still reach SSE
clients via ``run_events``, run-lifecycle §8 "Redis loss").
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

import redis

log = logging.getLogger(__name__)

QUEUE_CHANNEL = "hibiscus:queue"


def run_channel(run_id: str) -> str:
    return f"hibiscus:run:{run_id}"


def workspace_channel(workspace_id: str) -> str:
    return f"hibiscus:ws:{workspace_id}"


def control_channel(gpu_id: str) -> str:
    return f"hibiscus:control:{gpu_id}"


def _json_default(o: object) -> object:
    return str(o)


def sanitize(value: Any) -> Any:
    """Replace non-finite floats by ``None`` (JSON has no NaN/Inf; spec: NaN/Inf => null)."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [sanitize(v) for v in value]
    return value


def dumps(obj: Any) -> str:
    return json.dumps(sanitize(obj), default=_json_default, separators=(",", ":"), allow_nan=False)


class Bus:
    """Thin best-effort publisher."""

    def __init__(self, url: str) -> None:
        self.client: redis.Redis = redis.Redis.from_url(url, socket_timeout=2.0, socket_connect_timeout=2.0)

    def publish(self, channel: str, payload: dict[str, Any]) -> None:
        try:
            self.client.publish(channel, dumps(payload))
        except redis.RedisError as exc:
            log.warning("redis publish to %s failed: %s", channel, type(exc).__name__)

    def publish_run(self, run_id: str, event: str, data: dict[str, Any], seq: int | None = None) -> None:
        self.publish(run_channel(run_id), {"event": event, "id": seq, "data": data})

    def publish_workspace(self, workspace_id: str, event: str, data: dict[str, Any]) -> None:
        self.publish(workspace_channel(workspace_id), {"event": event, "data": data})

    def close(self) -> None:
        try:
            self.client.close()
        except redis.RedisError:
            pass
