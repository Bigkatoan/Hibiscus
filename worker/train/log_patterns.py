"""Frozen log-parsing contract for `lerobot-train` 0.7.1 output (see docs/spec/log-parsing.md).

This module is part of the v0.1 contract owned by A1. A4 (BE-Train) builds the streaming
parser/metrics pipeline on top of it but MUST NOT change the regexes or the step-resolution rule
without a contract change request.

Input model: the worker runs `lerobot-train` with stdout and stderr merged into ONE pipe
(``stderr=subprocess.STDOUT``) and ``PYTHONUNBUFFERED=1``. The byte stream mixes tqdm progress
updates (separated by ``\\r``, no newline) with logging lines (terminated by ``\\n``). A logging
line is frequently glued directly after a tqdm segment with no separator, e.g.::

    \\rTraining:   0%|          | 200/100000 [00:26<3:01:01,  9.19step/s]INFO 2026-11-14 ...

Therefore records are obtained by splitting on ``\\r`` and ``\\n`` and every record is scanned with
``finditer`` for BOTH a progress match and a log-line match, processed in positional order.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

# --- Pre-processing -------------------------------------------------------------------------------

#: ANSI SGR escape sequences (termcolor is used for "Output dir:" when attached to a TTY).
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

#: Record separator. Split the decoded stream on this (keep partial trailing record buffered).
RECORD_SPLIT_RE = re.compile(r"[\r\n]")

# --- Progress bar (tqdm, desc="Training", unit="step") ---------------------------------------------
#: ``n`` counts steps done IN THIS PROCESS (tqdm total = cfg.steps - initial_step on resume).
TQDM_RE = re.compile(
    r"Training:\s+(?P<pct>\d{1,3})%\|[^|]*\|\s*(?P<n>\d+)/(?P<total>\d+)\s+"
    r"\[(?P<elapsed>[0-9:]+)<(?P<remaining>[0-9:?]+),\s*(?P<rate>[0-9.]+|\?)(?P<rate_unit>step/s|s/step)\]"
)

# --- Python logging prefix used by lerobot (init_logging) -------------------------------------------
#: Formatter (lerobot.utils.utils.init_logging):
#: ``"%(levelname)s %(lerobot_pid)s%(asctime)s %(lerobot_location)15s %(message)s"`` where
#: ``lerobot_location = f"{pathname}:{lineno}"[-15:]`` (right-aligned to 15 chars, so it may be
#: space-padded or truncated, e.g. ``ot_train.py:894``) and ``lerobot_pid`` is ``"[PID: n] "`` only
#: on non-main distributed ranks.
LOG_PREFIX = (
    r"(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL) (?:\[PID: (?P<pid>\d+)\] )?"
    r"(?P<date>\d{4}-\d{2}-\d{2}) (?P<time>\d{2}:\d{2}:\d{2}) +(?P<src>\S*):(?P<lineno>\d+) "
)
LOG_LINE_RE = re.compile(LOG_PREFIX + r"(?P<msg>.*)$")

# --- Training metrics line (MetricsTracker.__str__) -------------------------------------------------
#: ``step`` / ``smpl`` / ``ep`` use format_big_number(precision=0) => ROUNDED, never use as step.
BIG_NUMBER = r"-?\d+(?:\.\d+)?[KMBTQ]?"
METRICS_MSG_RE = re.compile(
    r"^step:(?P<step_label>" + BIG_NUMBER + r") smpl:(?P<smpl>" + BIG_NUMBER + r") "
    r"ep:(?P<ep>" + BIG_NUMBER + r") epch:(?P<epch>-?\d+\.\d+) (?P<rest>.*)$"
)
#: One ``name:value`` meter token in ``rest``. Names seen in 0.7.1: loss grdn lr data_s prep_s updt_s
#: step_s smp/s scale mem_gb plus policy sub-losses (l1_loss, kld_loss, ...). Values may be
#: ``nan``/``inf``/``-inf`` (Python float formatting), or scientific (``lr:1.0e-05``).
METRIC_TOKEN_RE = re.compile(
    r"(?P<key>[A-Za-z_][A-Za-z0-9_./]*):(?P<value>-?(?:nan|inf|\d+(?:\.\d*)?(?:[eE][+-]?\d+)?))(?=\s|$)"
)

# --- Other structured messages -------------------------------------------------------------------
CFG_STEPS_RE = re.compile(r"^cfg\.steps=(?P<steps>\d+) ")
NUM_FRAMES_RE = re.compile(r"^dataset\.num_frames=(?P<n>\d+) ")
NUM_EPISODES_RE = re.compile(r"^dataset\.num_episodes=(?P<n>\d+)$")
EFFECTIVE_BS_RE = re.compile(
    r"^Effective batch size: (?P<bs>\d+) x (?P<dp>\d+) dp workers x (?P<accum>\d+) grad accum = (?P<eff>\d+)"
)
LEARNABLE_PARAMS_RE = re.compile(r"^num_learnable_params=(?P<n>\d+) ")
TOTAL_PARAMS_RE = re.compile(r"^num_total_params=(?P<n>\d+) ")
OUTPUT_DIR_RE = re.compile(r"^Output dir: (?P<path>\S.*)$")
TRAINING_START_RE = re.compile(
    r"^Start offline training on a fixed dataset, with effective batch size: (?P<eff>\d+)$"
)
CHECKPOINT_RE = re.compile(r"^Checkpoint policy after step (?P<step>\d+)$")
CHECKPOINT_SAVED_RE = re.compile(r"^Model weights successfully saved to (?P<path>\S+)/pretrained_model!?$")
EVAL_LOSS_RE = re.compile(
    r"^step (?P<step>\d+): eval_loss=(?P<value>-?(?:nan|inf|\d+(?:\.\d*)?(?:[eE][+-]?\d+)?))$"
)
END_OF_TRAINING_RE = re.compile(r"^End of training$")

# --- Failure signatures (matched against any record, not only log lines) ---------------------------
OOM_RE = re.compile(
    r"(torch\.OutOfMemoryError|torch\.cuda\.OutOfMemoryError|CUDA out of memory|CUBLAS_STATUS_ALLOC_FAILED)"
)
TRACEBACK_RE = re.compile(r"^Traceback \(most recent call last\):")
NCCL_OR_CUDA_FATAL_RE = re.compile(
    r"(CUDA error: |cudaErrorLaunchFailure|an illegal memory access was encountered|NVML_ERROR|Xid)"
)
DATA_ERROR_RE = re.compile(
    r"(FileNotFoundError|KeyError: 'observation\.|torchcodec.*(?:Error|error)"
    r"|Could not (?:decode|open) video)"
)

# Canonical metric keys stored in run_metrics (left = token key in log, right = stored key).
METRIC_KEY_MAP: dict[str, str] = {
    "loss": "loss",
    "grdn": "grad_norm",
    "lr": "lr",
    "data_s": "data_s",
    "prep_s": "prep_s",
    "updt_s": "update_s",
    "step_s": "step_s",
    "smp/s": "samples_per_s",
    "scale": "grad_scale",
    "mem_gb": "gpu_mem_gb",
}
"""Unknown keys (policy sub-losses such as ``l1_loss``) are stored verbatim after validating
``^[a-z][a-z0-9_]{0,63}$`` (lower-cased, ``/`` and ``.`` replaced by ``_``)."""

_SUFFIX = {"": 1, "K": 10**3, "M": 10**6, "B": 10**9, "T": 10**12, "Q": 10**15}


def format_big_number(num: float, precision: int = 0) -> str:
    """Exact re-implementation of lerobot.utils.utils.format_big_number (0.7.1)."""
    value = float(num)
    for suffix in _SUFFIX:
        if abs(value) < 1000.0:
            return f"{value:.{precision}f}{suffix}"
        value /= 1000.0
    return str(value)


def canonical_metric_key(key: str) -> str:
    if key in METRIC_KEY_MAP:
        return METRIC_KEY_MAP[key]
    return key.lower().replace("/", "_").replace(".", "_")


def parse_metric_value(text: str) -> float:
    return float(text)  # float() accepts "nan", "inf", "-inf" and scientific notation


def resolve_step(
    *, prev_step: int, log_freq: int, step_label: str, tqdm_step: int | None
) -> tuple[int, bool]:
    """Return (real_step, consistent) for a metrics line. Contract rule (log-parsing.md §4).

    lerobot logs exactly when ``step % log_freq == 0`` (step counted from ``initial_step``), so the
    k-th metrics line after ``prev_step`` is at the next multiple of ``log_freq``. ``consistent`` is
    False when the rounded label or the tqdm cross-check disagrees; the caller then emits a
    ``parser_warning`` run event but still stores the resolved step.
    """
    real = (prev_step // log_freq + 1) * log_freq
    consistent = format_big_number(real) == step_label
    if tqdm_step is not None and not (real - log_freq < tqdm_step <= real):
        consistent = False
    return real, consistent


@dataclass(slots=True)
class MetricsRecord:
    step: int
    step_label: str
    values: dict[str, float]
    consistent: bool
    log_time: str


@dataclass(slots=True)
class ParseResult:
    total_steps: int | None = None
    num_frames: int | None = None
    num_episodes: int | None = None
    effective_batch_size: int | None = None
    num_learnable_params: int | None = None
    metrics: list[MetricsRecord] = field(default_factory=list)
    checkpoints: list[int] = field(default_factory=list)
    eval_losses: list[tuple[int, float]] = field(default_factory=list)
    last_progress_step: int | None = None
    oom: bool = False
    traceback: bool = False


def iter_records(chunks: Iterable[str]) -> Iterator[str]:
    """Split a decoded text stream into records on \\r / \\n, buffering a partial tail."""
    buf = ""
    for chunk in chunks:
        buf += chunk
        parts = RECORD_SPLIT_RE.split(buf)
        buf = parts.pop()
        yield from (p for p in parts if p)
    if buf:
        yield buf


def parse_stream(chunks: Iterable[str], *, log_freq: int, initial_step: int = 0) -> ParseResult:
    """Reference (batch) implementation of the contract; A4's live parser must be equivalent."""
    res = ParseResult()
    prev_step = initial_step
    tqdm_step: int | None = None
    for raw in iter_records(chunks):
        record = ANSI_RE.sub("", raw)
        if OOM_RE.search(record):
            res.oom = True
        if TRACEBACK_RE.search(record):
            res.traceback = True
        progress = list(TQDM_RE.finditer(record))
        log_match = None
        log_pos = record.find("INFO ")
        if log_pos < 0:
            for level in ("WARNING ", "ERROR ", "CRITICAL ", "DEBUG "):
                log_pos = record.find(level)
                if log_pos >= 0:
                    break
        if log_pos >= 0:
            log_match = LOG_LINE_RE.match(record, log_pos)
        for m in progress:
            if log_match is None or m.start() < log_match.start():
                tqdm_step = initial_step + int(m.group("n"))
                res.last_progress_step = tqdm_step
        if log_match is None:
            continue
        msg = log_match.group("msg")
        if mm := METRICS_MSG_RE.match(msg):
            values = {
                canonical_metric_key(t.group("key")): parse_metric_value(t.group("value"))
                for t in METRIC_TOKEN_RE.finditer(mm.group("rest"))
            }
            step, ok = resolve_step(
                prev_step=prev_step, log_freq=log_freq, step_label=mm.group("step_label"), tqdm_step=tqdm_step
            )
            prev_step = step
            res.metrics.append(
                MetricsRecord(
                    step, mm.group("step_label"), values, ok, f"{log_match['date']}T{log_match['time']}"
                )
            )
        elif m2 := CFG_STEPS_RE.match(msg):
            res.total_steps = int(m2.group("steps"))
        elif m2 := NUM_FRAMES_RE.match(msg):
            res.num_frames = int(m2.group("n"))
        elif m2 := NUM_EPISODES_RE.match(msg):
            res.num_episodes = int(m2.group("n"))
        elif m2 := EFFECTIVE_BS_RE.match(msg):
            res.effective_batch_size = int(m2.group("eff"))
        elif m2 := LEARNABLE_PARAMS_RE.match(msg):
            res.num_learnable_params = int(m2.group("n"))
        elif m2 := CHECKPOINT_RE.match(msg):
            res.checkpoints.append(int(m2.group("step")))
        elif m2 := EVAL_LOSS_RE.match(msg):
            res.eval_losses.append((int(m2.group("step")), parse_metric_value(m2.group("value"))))
        # Progress segments that come AFTER the log line within the same record (rare) still count.
        for m in progress:
            if m.start() > log_match.start():
                tqdm_step = initial_step + int(m.group("n"))
                res.last_progress_step = tqdm_step
    return res
