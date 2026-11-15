#!/usr/bin/env python3
"""Stand-in for ``lerobot-train`` 0.7.1 used by the non-GPU runner tests.

Reproduces the byte-level output format (tqdm ``\\r`` frames glued to logging lines, metrics lines,
checkpoint messages) and the on-disk checkpoint layout (``checkpoints/<NNNNNN>/{pretrained_model,
training_state}`` + ``last`` symlink) of the real script, honouring ``--steps``, ``--log_freq``,
``--save_freq``, ``--output_dir`` and ``--config_path ... --resume=true``.

Behaviour switches (env): FAKE_MODE = normal | nan | crash | config_error | oom | silent | sigterm_ignore,
FAKE_STEP_S (seconds per step, default 0.005), FAKE_CRASH_AT (step, default 30).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def arg(name: str, default: str | None = None) -> str | None:
    for a in sys.argv[1:]:
        if a.startswith(f"--{name}="):
            return a.split("=", 1)[1]
    return default


def big(n: float) -> str:
    v = float(n)
    for suf in ("", "K", "M", "B", "T", "Q"):
        if abs(v) < 1000.0:
            return f"{v:.0f}{suf}"
        v /= 1000.0
    return str(v)


def log(msg: str, src: str = "ot_train.py:894") -> None:
    sys.stdout.write(f"INFO {time.strftime('%Y-%m-%d %H:%M:%S')} {src:>15} {msg}\n")
    sys.stdout.flush()


def main() -> int:
    mode = os.environ.get("FAKE_MODE", "normal")
    step_s = float(os.environ.get("FAKE_STEP_S", "0.005"))
    if mode == "config_error":
        sys.stdout.write(
            "Traceback (most recent call last):\n"
            '  File "/x/lerobot/scripts/lerobot_train.py", line 1073, in main\n'
            '  File "/x/draccus/parsers/decoding.py", line 179, in decode_dataclass\n'
            "draccus.utils.ParsingError: Couldn't instantiate class ACTConfig using the given arguments.\n"
        )
        return 1
    initial = 0
    resume = arg("resume") == "true"
    if resume:
        cfg_path = Path(arg("config_path") or "")
        ckpt = cfg_path.parent.parent
        initial = int(json.loads((ckpt / "training_state" / "training_step.json").read_text())["step"])
        cfg = json.loads(cfg_path.read_text())
        out = Path(cfg["output_dir"])
        log_freq, save_freq = int(cfg["log_freq"]), int(cfg["save_freq"])
    else:
        out = Path(arg("output_dir") or "out")
        if out.exists():
            sys.stdout.write(f"FileExistsError: Output directory {out} already exists\n")
            return 1
        log_freq, save_freq = int(arg("log_freq", "200") or 200), int(arg("save_freq", "10000") or 10000)
    steps = int(arg("steps", "100") or 100)
    log(f"Output dir: {out}", "ot_train.py:600")
    log(f"cfg.steps={steps} ({big(steps)})", "ot_train.py:610")
    log("dataset.num_frames=11277 (11K)", "ot_train.py:611")
    log("dataset.num_episodes=20", "ot_train.py:612")
    log("Effective batch size: 8 x 1 dp workers x 1 grad accum = 8 (8 / 8 per dp worker)", "ot_train.py:613")
    log("Start offline training on a fixed dataset, with effective batch size: 8", "ot_train.py:700")
    total = steps - initial
    sys.stderr.write(f"\rTraining:   0%|          | 0/{total} [00:00<?, ?step/s]")
    sys.stderr.flush()
    for i in range(1, total + 1):
        step = initial + i
        time.sleep(step_s)
        if mode == "silent" and i == 5:
            time.sleep(3600)
        if mode == "crash" and step == int(os.environ.get("FAKE_CRASH_AT", "30")):
            sys.stdout.write('Traceback (most recent call last):\n  File "/x/y.py"\nRuntimeError: boom\n')
            sys.stdout.flush()
            return 1
        if mode == "oom" and step == 15:
            sys.stdout.write(
                "Traceback (most recent call last):\ntorch.OutOfMemoryError: CUDA out of memory.\n"
            )
            sys.stdout.flush()
            return 1
        pct = int(100 * i / total)
        sys.stderr.write(f"\rTraining: {pct:3d}%|#         | {i}/{total} [00:01<00:01, 50.00step/s]")
        sys.stderr.flush()
        if step % log_freq == 0:
            loss = "nan" if mode == "nan" else f"{1.0 / step:.3f}"
            sys.stderr.flush()
            sys.stdout.write(
                f"INFO {time.strftime('%Y-%m-%d %H:%M:%S')} ot_train.py:894 step:{big(step)} smpl:{big(step * 8)} "  # noqa: E501
                f"ep:0 epch:{step * 8 / 11277:.2f} loss:{loss} grdn:1.234 lr:1.0e-05 data_s:0.001 prep_s:0.000 "  # noqa: E501
                f"updt_s:0.010 step_s:0.011 smp/s:700 mem_gb:1.50 l1_loss:0.500 kld_loss:0.100\n"
            )
            sys.stdout.flush()
        if step % save_freq == 0 or step == steps:
            log(f"Checkpoint policy after step {step}", "ot_train.py:936")
            d = out / "checkpoints" / f"{step:06d}"
            (d / "pretrained_model").mkdir(parents=True, exist_ok=True)
            (d / "training_state").mkdir(parents=True, exist_ok=True)
            (d / "pretrained_model" / "config.json").write_text(json.dumps({"type": "act"}))
            (d / "pretrained_model" / "model.safetensors").write_bytes(os.urandom(2048))
            (d / "pretrained_model" / "train_config.json").write_text(
                json.dumps(
                    {"output_dir": str(out), "log_freq": log_freq, "save_freq": save_freq, "steps": steps}
                )
            )
            (d / "training_state" / "optimizer_state.safetensors").write_bytes(os.urandom(4096))
            (d / "training_state" / "training_step.json").write_text(json.dumps({"step": step}))
            log(f"Model weights successfully saved to {d}/pretrained_model!", "n/_torch.py:299")
            last = out / "checkpoints" / "last"
            if last.is_symlink():
                last.unlink()
            last.symlink_to(f"{step:06d}")
    log("End of training", "t_train.py:1026")
    return 0


if __name__ == "__main__":
    if os.environ.get("FAKE_MODE") == "sigterm_ignore":
        import signal

        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    sys.exit(main())
