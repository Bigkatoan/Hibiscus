"""Contract tests for docs/spec/log-parsing.md against a REAL lerobot-train 0.7.1 log.

Fixture: fixtures/act_picknplace.log.gz = gzip of ~/lelab/outputs/train/act_picknplace.log
(ACT, batch_size=8, log_freq=200, steps=100000, killed after step 10123).
"""

from __future__ import annotations

import gzip
import math
from pathlib import Path

import pytest

from train.log_patterns import (
    CHECKPOINT_RE,
    LOG_LINE_RE,
    METRIC_TOKEN_RE,
    METRICS_MSG_RE,
    TQDM_RE,
    format_big_number,
    parse_stream,
    resolve_step,
)

FIXTURE = Path(__file__).parent / "fixtures" / "act_picknplace.log.gz"


def _chunks(data: str, size: int = 4096) -> list[str]:
    # Feed in small arbitrary chunks to prove the parser is robust to pipe read boundaries.
    return [data[i : i + size] for i in range(0, len(data), size)]


@pytest.fixture(scope="module")
def real_log() -> str:
    return gzip.decompress(FIXTURE.read_bytes()).decode("utf-8")


def test_real_log_header(real_log: str) -> None:
    res = parse_stream(_chunks(real_log), log_freq=200)
    assert res.total_steps == 100_000
    assert res.num_frames == 11_277
    assert res.num_episodes == 20
    assert res.effective_batch_size == 8
    assert res.num_learnable_params == 51_597_190
    assert res.oom is False


def test_real_log_steps_are_exact_not_rounded(real_log: str) -> None:
    res = parse_stream(_chunks(real_log, 777), log_freq=200)
    steps = [m.step for m in res.metrics]
    assert steps == list(range(200, 10_001, 200)), "50 metrics lines at every 200 steps"
    # The rounded labels prove why the label must never be used as the step.
    by_step = {m.step: m for m in res.metrics}
    assert by_step[1000].step_label == "1K"
    assert by_step[1200].step_label == "1K"
    assert by_step[4600].step_label == "5K"
    assert by_step[5000].step_label == "5K"
    # In this log tqdm printed every step, so the cross-check passes for every record.
    assert all(m.consistent for m in res.metrics)


def test_real_log_metric_values(real_log: str) -> None:
    res = parse_stream(_chunks(real_log), log_freq=200)
    first = res.metrics[0]
    assert first.step == 200
    assert first.log_time == "2026-11-14T22:55:18"
    assert first.values == {
        "loss": 7.017,
        "grad_norm": 158.158,
        "lr": 1.0e-05,
        "data_s": 0.019,
        "prep_s": 0.0,
        "update_s": 0.114,
        "step_s": 0.134,
        "samples_per_s": 60.0,
        "gpu_mem_gb": 1.79,
        "l1_loss": 0.706,
        "kld_loss": 0.631,
    }
    at_5k = next(m for m in res.metrics if m.step == 5000)
    assert at_5k.values["loss"] == pytest.approx(0.347)
    assert at_5k.values["l1_loss"] == pytest.approx(0.155)
    assert at_5k.values["kld_loss"] == pytest.approx(0.019)
    assert at_5k.values["gpu_mem_gb"] == pytest.approx(1.78)


def test_real_log_checkpoint_and_progress(real_log: str) -> None:
    res = parse_stream(_chunks(real_log), log_freq=200)
    assert res.checkpoints == [10_000]
    assert res.last_progress_step == 10_123  # process was killed at 10123/100000


def test_tqdm_regex_variants() -> None:
    samples = {
        "Training:   0%|          | 0/100000 [00:00<?, ?step/s]": (0, 100000, "?", "step/s"),
        "Training:   0%|          | 1/100000 [00:05<142:46:47,  5.14s/step]": (1, 100000, "5.14", "s/step"),
        "Training:  10%|█         | 10001/100000 [18:23<6:13:22,  4.02step/s]": (
            10001,
            100000,
            "4.02",
            "step/s",
        ),
        "Training: 100%|██████████| 300/300 [00:41<00:00,  7.30step/s]": (300, 300, "7.30", "step/s"),
    }
    for text, (n, total, rate, unit) in samples.items():
        m = TQDM_RE.search(text)
        assert m is not None, text
        assert (int(m["n"]), int(m["total"]), m["rate"], m["rate_unit"]) == (n, total, rate, unit)


def test_log_prefix_variants() -> None:
    padded = "INFO 2026-11-14 23:13:14     train.py:12 Checkpoint policy after step 300"
    m = LOG_LINE_RE.match(padded)
    assert m and m["src"] == "train.py" and m["lineno"] == "12"
    assert CHECKPOINT_RE.match(m["msg"])["step"] == "300"  # type: ignore[index]
    pid = "WARNING [PID: 4242] 2026-11-14 23:13:14 ot_train.py:894 hello"
    m = LOG_LINE_RE.match(pid)
    assert m and m["pid"] == "4242" and m["msg"] == "hello"


def test_nan_inf_and_fp16_scale_tokens() -> None:
    msg = (
        "step:2K smpl:16K ep:28 epch:1.42 loss:nan grdn:inf lr:1.0e-04 scale:65536 mem_gb:9.10 kld_loss:-inf"
    )
    mm = METRICS_MSG_RE.match(msg)
    assert mm is not None
    vals = {t["key"]: float(t["value"]) for t in METRIC_TOKEN_RE.finditer(mm["rest"])}
    assert math.isnan(vals["loss"]) and math.isinf(vals["grdn"]) and vals["kld_loss"] == -math.inf
    assert vals["lr"] == 1.0e-04 and vals["scale"] == 65536.0


def test_resume_uses_initial_step() -> None:
    # On resume from step 10000, tqdm restarts at 0/90000 and MetricsTracker starts at 10000.
    log = (
        "\rTraining:   0%|          | 0/90000 [00:00<?, ?step/s]"
        "\rTraining:   0%|          | 200/90000 [00:22<2:44:00,  9.10step/s]"
        "INFO 2026-11-15 01:00:00 ot_train.py:894 step:10K smpl:82K ep:144 epch:7.27 loss:0.200 grdn:9.0 "
        "lr:1.0e-05 data_s:0.001 prep_s:0.000 updt_s:0.108 step_s:0.110 smp/s:73 mem_gb:1.78\n"
    )
    res = parse_stream([log], log_freq=200, initial_step=10_000)
    assert [m.step for m in res.metrics] == [10_200]
    assert res.metrics[0].consistent


def test_resolve_step_when_tqdm_lags() -> None:
    # Fast policies: tqdm (mininterval=0.1s) may not have printed n=400 before the metrics line.
    step, ok = resolve_step(prev_step=200, log_freq=200, step_label="400", tqdm_step=371)
    assert (step, ok) == (400, True)
    step, ok = resolve_step(prev_step=200, log_freq=200, step_label="1K", tqdm_step=371)
    assert (step, ok) == (400, False)


@pytest.mark.parametrize(
    ("n", "label"),
    [
        (200, "200"),
        (999, "999"),
        (1000, "1K"),
        (1499, "1K"),
        (1500, "2K"),
        (4600, "5K"),
        (100_000, "100K"),
        (2_500_000, "2M"),
    ],
)
def test_format_big_number_matches_lerobot(n: int, label: str) -> None:
    assert format_big_number(n) == label
