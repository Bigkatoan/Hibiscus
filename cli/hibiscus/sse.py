"""Server-Sent Events client with ``Last-Event-ID`` reconnect (operationId streamRunEvents).

Parsing follows the WHATWG EventSource algorithm (fields ``event``, ``data`` (multi-line),
``id``, ``retry``; comments start with ``:``). Reconnect policy:

* transport error / idle timeout / server closing the stream without ``event: end``
  -> reconnect after the server's ``retry:`` (default 3 s), growing on consecutive failures up to
  30 s, sending ``Last-Event-ID: <last persisted id>`` so the server replays missed events;
* 5xx / 429 -> same, honouring ``Retry-After``;
* other 4xx (401 / 403 / 404) -> :class:`hibiscus.api.ApiError` (not retryable);
* ``event: end`` -> stop.

The read timeout (default 45 s) is three heartbeats (contract: heartbeat every 15 s), so a dead
connection behind Cloudflare is detected and re-opened.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from hibiscus.api import ApiError, HibiscusApi, is_transport_error


@dataclass(frozen=True)
class SseMessage:
    event: str
    data: str
    id: str | None

    def json(self) -> Any:
        return json.loads(self.data) if self.data else None


class SseParser:
    """Incremental parser: feed lines (without terminators), get dispatched messages."""

    def __init__(self) -> None:
        self.last_event_id: str | None = None
        self.retry_ms: int | None = None
        self._event = ""
        self._data: list[str] = []
        self._id_seen: str | None = None

    def feed(self, line: str) -> SseMessage | None:
        if line == "":
            return self._dispatch()
        if line.startswith(":"):
            return None
        name, sep, value = line.partition(":")
        if sep and value.startswith(" "):
            value = value[1:]
        if name == "event":
            self._event = value
        elif name == "data":
            self._data.append(value)
        elif name == "id":
            if "\0" not in value:
                self._id_seen = value
                self.last_event_id = value
        elif name == "retry":
            if value.isdigit():
                self.retry_ms = int(value)
        return None

    def _dispatch(self) -> SseMessage | None:
        msg_id = self._id_seen
        self._id_seen = None
        if not self._data and not self._event:
            return None
        msg = SseMessage(event=self._event or "message", data="\n".join(self._data), id=msg_id)
        self._event = ""
        self._data = []
        return msg


def iter_sse_lines(lines: Iterable[str]) -> Iterator[SseMessage]:
    parser = SseParser()
    for line in lines:
        msg = parser.feed(line)
        if msg is not None:
            yield msg


class RunEventStream:
    """Follow ``GET /runs/{run_id}/events`` across disconnects."""

    def __init__(
        self,
        api: HibiscusApi,
        run_id: str,
        *,
        include: list[str] | None = None,
        last_event_id: str | None = None,
        read_timeout: float = 45.0,
        max_reconnect_delay: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        on_reconnect: Callable[[int, str, float], None] = lambda n, why, delay: None,
        max_reconnects: int | None = None,
    ) -> None:
        self.api = api
        self.run_id = run_id
        self.include = include
        self.last_event_id = last_event_id
        self.read_timeout = read_timeout
        self.max_reconnect_delay = max_reconnect_delay
        self.sleep = sleep
        self.on_reconnect = on_reconnect
        self.max_reconnects = max_reconnects
        self.retry_ms = 3000
        self.reconnects = 0
        self.ended = False

    def _params(self) -> dict[str, str]:
        return {"include": ",".join(self.include)} if self.include else {}

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}
        if self.last_event_id is not None:
            h["Last-Event-ID"] = self.last_event_id
        return h

    def __iter__(self) -> Iterator[SseMessage]:
        failures = 0
        while not self.ended:
            why = ""
            retry_after: float | None = None
            try:
                with self.api.stream(
                    "GET",
                    f"/runs/{self.run_id}/events",
                    params=self._params(),
                    headers=self._headers(),
                    timeout=httpx.Timeout(self.read_timeout, connect=15.0),
                ) as resp:
                    if resp.status_code != 200:
                        resp.read()
                        err = ApiError.from_http(resp.status_code, resp.content, resp.headers)
                        if not err.retryable:
                            raise err
                        why, retry_after = str(err), err.retry_after_s
                    else:
                        parser = SseParser()
                        for line in resp.iter_lines():
                            msg = parser.feed(line)
                            if parser.retry_ms is not None:
                                self.retry_ms = parser.retry_ms
                            if msg is None:
                                continue
                            failures = 0
                            if msg.id is not None:
                                self.last_event_id = msg.id
                            yield msg
                            if msg.event == "end":
                                self.ended = True
                                return
                        why = "stream closed by server"
            except ApiError:
                raise
            except Exception as exc:
                if not is_transport_error(exc):
                    raise
                why = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            failures += 1
            self.reconnects += 1
            if self.max_reconnects is not None and self.reconnects > self.max_reconnects:
                raise ApiError(0, "stream_lost", f"gave up after {self.max_reconnects} reconnects ({why})")
            delay = min(self.max_reconnect_delay, (self.retry_ms / 1000.0) * (2 ** max(0, failures - 1)))
            if retry_after is not None:
                delay = max(delay, retry_after)
            self.on_reconnect(self.reconnects, why, delay)
            self.sleep(delay)
