"""LiveParser == contract reference parser (log_patterns.parse_stream) on the real lerobot log."""

from __future__ import annotations

import gzip
import math
import random
from pathlib import Path

import pytest

from train.log_patterns import parse_stream
from train.parser import (
    CheckpointSaved,
    CheckpointStarted,
    EndOfTraining,
    Header,
    LiveParser,
    LogCollapser,
    Metrics,
    OutputDir,
    Progress,
    Signature,
    TrainingStart,
)

FIXTURE = Path(__file__).parent / "fixtures" / "act_picknplace.log.gz"


@pytest.fixture(scope="module")
def real_log() -> str:
    return gzip.decompress(FIXTURE.read_bytes()).decode("utf-8")


def _random_chunks(data: str, seed: int) -> list[str]:
    rnd = random.Random(seed)  # noqa: S311 - test chunking only
    out, i = [], 0
    while i < len(data):
        n = rnd.choice([1, 7, 64, 513, 4096, 65536])
        out.append(data[i : i + n])
        i += n
    return out


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_live_parser_matches_reference(real_log: str, seed: int) -> None:
    ref = parse_stream([real_log], log_freq=200)
    p = LiveParser(log_freq=200)
    events = []
    for c in _random_chunks(real_log, seed):
        events.extend(p.feed(c))
    events.extend(p.close())
    metrics = [e for e in events if isinstance(e, Metrics)]
    assert [m.step for m in metrics] == [m.step for m in ref.metrics]
    for a, b in zip(metrics, ref.metrics, strict=True):
        assert a.consistent == b.consistent
        assert a.step_label == b.step_label
        for k, v in b.values.items():
            assert (math.isnan(v) and math.isnan(a.values[k])) or a.values[k] == v
    first = metrics[0].values
    assert first["loss"] == 7.017 and first["grad_norm"] == 158.158 and first["lr"] == 1e-05
    assert first["l1_loss"] == 0.706 and first["kld_loss"] == 0.631 and first["gpu_mem_gb"] == 1.79
    progress = [e for e in events if isinstance(e, Progress)]
    assert progress[-1].step == ref.last_progress_step == 10123
    assert [e.step for e in events if isinstance(e, CheckpointStarted)] == ref.checkpoints == [10000]
    headers = {e.key: e.value for e in events if isinstance(e, Header)}
    assert headers == {
        "total_steps": 100_000,
        "num_frames": 11_277,
        "num_episodes": 20,
        "effective_batch_size": 8,
        "num_learnable_params": 51_597_190,
    }
    assert sum(isinstance(e, TrainingStart) for e in events) == 1
    assert any(isinstance(e, OutputDir) for e in events)
    saved = [e for e in events if isinstance(e, CheckpointSaved)]
    assert saved and saved[0].path.endswith("checkpoints/010000")
    assert not any(isinstance(e, Signature) and e.kind == "oom" for e in events)


def test_resume_initial_step_offsets_tqdm() -> None:
    text = (
        "\rTraining:   0%|          | 0/100 [00:00<?, ?step/s]"
        "\rTraining:  10%|#         | 10/100 [00:01<00:09, 10.0step/s]"
        "INFO 2026-11-15 10:00:00 ot_train.py:894 step:510 smpl:4K ep:5 epch:0.36 "
        "loss:nan grdn:1.0 lr:1.0e-05\n"
        "\rTraining:  20%|##        | 20/100 [00:02<00:08,  2.50s/step]"
        "INFO 2026-11-15 10:00:01 ot_train.py:894 step:520 smpl:4K ep:5 epch:0.37 "
        "loss:inf grdn:1.0 lr:1.0e-05\n"
        "INFO 2026-11-15 10:00:02 t_train.py:1026 End of training\n"
    )
    p = LiveParser(log_freq=10, initial_step=500)
    ev = p.feed(text) + p.close()
    m = [e for e in ev if isinstance(e, Metrics)]
    assert [x.step for x in m] == [510, 520]
    assert all(x.consistent for x in m)
    assert math.isnan(m[0].values["loss"]) and math.isinf(m[1].values["loss"])
    prog = [e for e in ev if isinstance(e, Progress)]
    assert prog[0].step == 500 and prog[0].steps_per_s is None
    assert prog[1].step == 510 and prog[1].steps_per_s == 10.0 and prog[1].remaining_s == 9.0
    assert prog[2].steps_per_s == pytest.approx(0.4)
    assert isinstance(ev[-1], EndOfTraining)


def test_signatures_detected() -> None:
    p = LiveParser(log_freq=10)
    ev = p.feed("Traceback (most recent call last):\n  x\ntorch.OutOfMemoryError: CUDA out of memory.\n")
    kinds = {e.kind for e in ev if isinstance(e, Signature)}
    assert kinds == {"traceback", "oom"}


def test_collapser_keeps_last_frame() -> None:
    c = LogCollapser()
    out = c.feed("a\rb\rc")
    assert out == []
    out = c.feed("INFO x\nnext\r")
    assert out == ["cINFO x"]
    out = c.feed("\rframe1\rframe2")
    assert out == []
    assert c._pending.endswith("frame2") and "frame1" not in c._pending
    assert c.close() == ["frame2"]


def test_collapser_on_real_log(real_log: str) -> None:
    c = LogCollapser()
    lines = []
    for ch in _random_chunks(real_log, 5):
        lines.extend(c.feed(ch))
    lines.extend(c.close())
    assert not any("\r" in ln for ln in lines)
    metric_lines = [ln for ln in lines if " step:" in ln and "smpl:" in ln]
    assert len(metric_lines) == 50


def test_real_smolvla_log_keys_and_steps() -> None:
    """Real lerobot-train 0.7.1 SmolVLA fine-tune (20 steps, bs 8, RTX 3060) recorded by A4."""
    raw = gzip.decompress((FIXTURE.parent / "smolvla_20steps_rtx3060.log.gz").read_bytes()).decode()
    p = LiveParser(log_freq=10)
    ev = []
    for c in _random_chunks(raw, 9):
        ev.extend(p.feed(c))
    ev.extend(p.close())
    m = [e for e in ev if isinstance(e, Metrics)]
    assert [x.step for x in m] == [10, 20] and all(x.consistent for x in m)
    assert {"losses_after_forward", "losses_after_rm_padding", "gpu_mem_gb"} <= set(m[-1].values)
    assert m[-1].values["gpu_mem_gb"] == 2.34
    assert any(isinstance(e, EndOfTraining) for e in ev)
