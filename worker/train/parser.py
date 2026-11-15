"""Streaming parser for ``lerobot-train`` output (docs/spec/log-parsing.md).

:class:`LiveParser` is the incremental equivalent of :func:`train.log_patterns.parse_stream`
(the contract's reference implementation): it is fed decoded text chunks as they are read from
the process pipe and returns typed events in stream order. ``train/tests/test_parser.py`` proves
the equivalence on the real 10k-step log fed in random chunk sizes.

:class:`LogCollapser` produces the stored/streamed log lines: tqdm ``\\r`` frames are collapsed to
the last frame before a ``\\n`` (run-lifecycle §9).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from train.log_patterns import (
    ANSI_RE,
    CFG_STEPS_RE,
    CHECKPOINT_RE,
    CHECKPOINT_SAVED_RE,
    DATA_ERROR_RE,
    EFFECTIVE_BS_RE,
    END_OF_TRAINING_RE,
    EVAL_LOSS_RE,
    LEARNABLE_PARAMS_RE,
    LOG_LINE_RE,
    METRIC_TOKEN_RE,
    METRICS_MSG_RE,
    NCCL_OR_CUDA_FATAL_RE,
    NUM_EPISODES_RE,
    NUM_FRAMES_RE,
    OOM_RE,
    OUTPUT_DIR_RE,
    RECORD_SPLIT_RE,
    TQDM_RE,
    TRACEBACK_RE,
    TRAINING_START_RE,
    canonical_metric_key,
    parse_metric_value,
    resolve_step,
)

KEY_RE_OK = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


# --- events ---------------------------------------------------------------------------------------
@dataclass(slots=True, frozen=True)
class Progress:
    step: int  # initial_step + tqdm n
    total: int  # tqdm total (steps remaining in this process)
    steps_per_s: float | None
    remaining_s: float | None


@dataclass(slots=True, frozen=True)
class Metrics:
    step: int
    step_label: str
    values: dict[str, float]
    consistent: bool
    tqdm_step: int | None
    log_time: str


@dataclass(slots=True, frozen=True)
class Header:
    key: str  # total_steps | num_frames | num_episodes | effective_batch_size | num_learnable_params
    value: int


@dataclass(slots=True, frozen=True)
class OutputDir:
    path: str


@dataclass(slots=True, frozen=True)
class TrainingStart:
    effective_batch_size: int


@dataclass(slots=True, frozen=True)
class CheckpointStarted:
    step: int


@dataclass(slots=True, frozen=True)
class CheckpointSaved:
    path: str


@dataclass(slots=True, frozen=True)
class EvalLoss:
    step: int
    value: float


@dataclass(slots=True, frozen=True)
class EndOfTraining:
    pass


@dataclass(slots=True, frozen=True)
class Signature:
    kind: str  # oom | traceback | cuda_fatal | data_error
    text: str


Event = (
    Progress
    | Metrics
    | Header
    | OutputDir
    | TrainingStart
    | CheckpointStarted
    | CheckpointSaved
    | EvalLoss
    | EndOfTraining
    | Signature
)


def _parse_hms(text: str) -> float | None:
    if "?" in text:
        return None
    total = 0.0
    for part in text.split(":"):
        total = total * 60 + float(part)
    return total


@dataclass
class LiveParser:
    log_freq: int
    initial_step: int = 0
    prev_step: int = field(init=False)
    tqdm_step: int | None = field(default=None, init=False)
    _buf: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.prev_step = self.initial_step

    def feed(self, chunk: str) -> list[Event]:
        self._buf += chunk
        parts = RECORD_SPLIT_RE.split(self._buf)
        self._buf = parts.pop()
        out: list[Event] = []
        for p in parts:
            if p:
                out.extend(self._record(p))
        return out

    def close(self) -> list[Event]:
        tail, self._buf = self._buf, ""
        return self._record(tail) if tail else []

    # -- one record (same algorithm as log_patterns.parse_stream) -----------------------------------
    def _progress(self, m: re.Match[str]) -> Progress:
        self.tqdm_step = self.initial_step + int(m.group("n"))
        rate_s = m.group("rate")
        rate: float | None = None
        if rate_s != "?":
            r = float(rate_s)
            rate = r if m.group("rate_unit") == "step/s" else (1.0 / r if r > 0 else None)
        return Progress(self.tqdm_step, int(m.group("total")), rate, _parse_hms(m.group("remaining")))

    def _record(self, raw: str) -> list[Event]:
        out: list[Event] = []
        record = ANSI_RE.sub("", raw)
        if OOM_RE.search(record):
            out.append(Signature("oom", record[-500:]))
        if TRACEBACK_RE.search(record):
            out.append(Signature("traceback", record[-500:]))
        if NCCL_OR_CUDA_FATAL_RE.search(record):
            out.append(Signature("cuda_fatal", record[-500:]))
        if DATA_ERROR_RE.search(record):
            out.append(Signature("data_error", record[-500:]))
        progress = list(TQDM_RE.finditer(record))
        log_pos = record.find("INFO ")
        if log_pos < 0:
            for level in ("WARNING ", "ERROR ", "CRITICAL ", "DEBUG "):
                log_pos = record.find(level)
                if log_pos >= 0:
                    break
        log_match = LOG_LINE_RE.match(record, log_pos) if log_pos >= 0 else None
        for m in progress:
            if log_match is None or m.start() < log_match.start():
                out.append(self._progress(m))
        if log_match is None:
            return out
        msg = log_match.group("msg")
        if mm := METRICS_MSG_RE.match(msg):
            values: dict[str, float] = {}
            for t in METRIC_TOKEN_RE.finditer(mm.group("rest")):
                key = canonical_metric_key(t.group("key"))
                if KEY_RE_OK.match(key):
                    values[key] = parse_metric_value(t.group("value"))
            values["epoch"] = float(mm.group("epch"))
            step, ok = resolve_step(
                prev_step=self.prev_step,
                log_freq=self.log_freq,
                step_label=mm.group("step_label"),
                tqdm_step=self.tqdm_step,
            )
            self.prev_step = step
            out.append(
                Metrics(
                    step,
                    mm.group("step_label"),
                    values,
                    ok,
                    self.tqdm_step,
                    f"{log_match['date']}T{log_match['time']}",
                )
            )
        elif m2 := CFG_STEPS_RE.match(msg):
            out.append(Header("total_steps", int(m2.group("steps"))))
        elif m2 := NUM_FRAMES_RE.match(msg):
            out.append(Header("num_frames", int(m2.group("n"))))
        elif m2 := NUM_EPISODES_RE.match(msg):
            out.append(Header("num_episodes", int(m2.group("n"))))
        elif m2 := EFFECTIVE_BS_RE.match(msg):
            out.append(Header("effective_batch_size", int(m2.group("eff"))))
        elif m2 := LEARNABLE_PARAMS_RE.match(msg):
            out.append(Header("num_learnable_params", int(m2.group("n"))))
        elif m2 := OUTPUT_DIR_RE.match(msg):
            out.append(OutputDir(m2.group("path")))
        elif m2 := TRAINING_START_RE.match(msg):
            out.append(TrainingStart(int(m2.group("eff"))))
        elif m2 := CHECKPOINT_RE.match(msg):
            out.append(CheckpointStarted(int(m2.group("step"))))
        elif m2 := CHECKPOINT_SAVED_RE.match(msg):
            out.append(CheckpointSaved(m2.group("path")))
        elif m2 := EVAL_LOSS_RE.match(msg):
            out.append(EvalLoss(int(m2.group("step")), parse_metric_value(m2.group("value"))))
        elif END_OF_TRAINING_RE.match(msg):
            out.append(EndOfTraining())
        for m in progress:
            if m.start() > log_match.start():
                out.append(self._progress(m))
        return out


def is_finite(v: float) -> bool:
    return math.isfinite(v)


class LogCollapser:
    """Turn the raw stream into stored lines: within a line, keep only the last ``\\r`` segment.

    ``feed`` returns completed lines (without the trailing newline). Memory is bounded: the
    pending buffer is truncated to the text after its last ``\\r`` as soon as it is seen.
    """

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, chunk: str) -> list[str]:
        data = self._pending + chunk
        lines = data.split("\n")
        self._pending = lines.pop()
        cr = self._pending.rfind("\r")
        if cr >= 0:
            # keep the possibly-incomplete last frame only
            self._pending = self._pending[cr + 1 :] if cr + 1 < len(self._pending) else self._pending[cr:]
        out: list[str] = []
        for line in lines:
            segs = [s for s in line.split("\r") if s]
            out.append(ANSI_RE.sub("", segs[-1]) if segs else "")
        return out

    def close(self) -> list[str]:
        tail, self._pending = self._pending, ""
        segs = [s for s in tail.split("\r") if s]
        return [ANSI_RE.sub("", segs[-1])] if segs else []
