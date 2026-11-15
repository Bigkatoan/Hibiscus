"""``hibiscus logs [-f] <run>`` (operationIds getRun, getRunLogs, streamRunEvents).

The stored log is byte-addressed. We print it (or its last ``tail`` lines), remember the byte
position, then follow SSE ``log`` events whose ``byte_offset`` says where their lines live in the
stored log. Lines before our position are skipped (dedupe after a reconnect replay); a jump past our
position (events lost while disconnected — ``log`` events are ephemeral and not replayed) is filled
with ``GET /runs/{id}/logs`` + ``Range: bytes=<pos>-<offset-1>``. Persisted events (status, error,
warning, checkpoint, model, eval, metrics) are replayed by the server via ``Last-Event-ID``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hibiscus.api import ApiError, HibiscusApi
from hibiscus.sse import RunEventStream, SseMessage

TERMINAL = {"succeeded", "failed", "cancelled"}


@dataclass
class LogSink:
    line: Callable[[str], None]
    event: Callable[[str, str], None]  # (kind, text)


class LogFollower:
    def __init__(
        self,
        api: HibiscusApi,
        run_id: str,
        sink: LogSink,
        *,
        show_metrics: bool = False,
        stream_factory: Callable[[HibiscusApi, str], RunEventStream] | None = None,
    ) -> None:
        self.api = api
        self.run_id = run_id
        self.sink = sink
        self.show_metrics = show_metrics
        self.pos = 0
        self.final_status: str | None = None
        self._stream_factory = stream_factory or (
            lambda a, r: RunEventStream(a, r, include=["log"], on_reconnect=self._on_reconnect)
        )

    def _on_reconnect(self, n: int, why: str, delay: float) -> None:
        self.sink.event("reconnect", f"connection lost ({why}); reconnecting in {delay:.0f}s (#{n})")

    # ------------------------------------------------------------------ stored log
    def fetch_range(self, start: int, end: int | None = None) -> bytes:
        rng = f"bytes={start}-" + (str(end) if end is not None else "")
        try:
            resp = self.api.request(
                "GET", f"/runs/{self.run_id}/logs", headers={"Range": rng}, expect=(200, 206)
            )
        except ApiError as exc:
            if exc.status == 416:
                return b""
            raise
        if resp.status_code == 200:
            # server ignored Range: slice locally
            body = resp.content
            return body[start : (end + 1) if end is not None else None]
        return resp.content

    def print_existing(self, tail: int | None) -> None:
        data = self.fetch_range(0)
        self.pos = len(data)
        text = data.decode("utf-8", "replace")
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        if tail is not None:
            lines = lines[-tail:] if tail > 0 else []
        for ln in lines:
            self.sink.line(ln)

    # ------------------------------------------------------------------ live
    def _on_log(self, data: dict[str, Any]) -> None:
        offset = int(data.get("byte_offset", 0))
        if offset > self.pos:
            gap = self.fetch_range(self.pos, offset - 1)
            text = gap.decode("utf-8", "replace")
            for ln in text.split("\n")[:-1] if text.endswith("\n") else text.split("\n"):
                self.sink.line(ln)
            self.pos += len(gap)
        for ln in data.get("lines", []):
            n = len(str(ln).encode("utf-8")) + 1
            if offset >= self.pos:
                self.sink.line(str(ln))
                self.pos = offset + n
            offset += n

    def handle(self, msg: SseMessage) -> bool:
        """Process one message; returns False when the stream is finished."""
        if msg.event == "heartbeat":
            return True
        data = msg.json() or {}
        if msg.event == "log":
            self._on_log(data)
        elif msg.event == "status":
            reason = f" ({data['reason']})" if data.get("reason") else ""
            self.sink.event("status", f"{data.get('from') or '-'} -> {data.get('to')}{reason}")
        elif msg.event == "error":
            retry = " (will retry)" if data.get("will_retry") else ""
            self.sink.event("error", f"{data.get('code')}: {data.get('message')}{retry}")
        elif msg.event == "warning":
            self.sink.event("warning", f"{data.get('code')}: {data.get('message')}")
        elif msg.event == "checkpoint":
            self.sink.event("checkpoint", f"checkpoint saved at step {data.get('step')}")
        elif msg.event == "model":
            v = " verified" if data.get("verified") else ""
            self.sink.event("model", f"model {data.get('model_id')} {data.get('status')}{v}")
        elif msg.event == "eval":
            self.sink.event("eval", f"eval step {data.get('step')}: action_mae={data.get('action_mae')}")
        elif msg.event == "metrics" and self.show_metrics:
            vals = data.get("values") or {}
            shown = ", ".join(
                f"{k}={v:.4g}" if isinstance(v, (int, float)) else f"{k}={v}" for k, v in vals.items()
            )
            self.sink.event("metrics", f"step {data.get('step')}: {shown}")
        elif msg.event == "end":
            self.final_status = str(data.get("final_status"))
            self.sink.event("end", f"run finished: {self.final_status}")
            return False
        return True

    def follow(self) -> str | None:
        for msg in self._stream_factory(self.api, self.run_id):
            if not self.handle(msg):
                break
        return self.final_status
