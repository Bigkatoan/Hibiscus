"""Turn ``runs.resolved_args`` (API-built, with placeholders) into the real argv (run-lifecycle §3, §10)."""

from __future__ import annotations

from pathlib import Path

DATASET_ROOT = "{{DATASET_ROOT}}"
OUTPUT_DIR = "{{OUTPUT_DIR}}"
INIT_PATH = "{{INIT_PATH}}"
MP_FLAG = "--accelerator.mixed_precision="


def mp_value(mp: str) -> str:
    """draccus/YAML reads a bare ``no`` as ``False``: always quote (verified on lerobot 0.7.1)."""
    return f'"{mp}"'


def finalize_fresh(
    resolved_args: list[str],
    *,
    bin_path: str,
    dataset_root: Path,
    output_dir: Path,
    init_path: Path | str | None,
    mixed_precision: str,
    max_num_workers: int = 4,
) -> list[str]:
    out: list[str] = [bin_path]
    saw_mp = False
    for arg in resolved_args[1:]:
        if arg.startswith(MP_FLAG):
            out.append(MP_FLAG + mp_value(mixed_precision))
            saw_mp = True
            continue
        if arg.startswith("--num_workers="):
            out.append(f"--num_workers={min(int(arg.split('=', 1)[1]), max_num_workers)}")
            continue
        if INIT_PATH in arg:
            if init_path is None:
                continue
            arg = arg.replace(INIT_PATH, str(init_path))
        out.append(arg.replace(DATASET_ROOT, str(dataset_root)).replace(OUTPUT_DIR, str(output_dir)))
    if not saw_mp:
        out.append(MP_FLAG + mp_value(mixed_precision))
    return out


def finalize_resume(
    *, bin_path: str, output_dir: Path, step: int, total_steps: int, mixed_precision: str
) -> list[str]:
    cfg = output_dir / "checkpoints" / f"{step:06d}" / "pretrained_model" / "train_config.json"
    return [
        bin_path,
        f"--config_path={cfg}",
        "--resume=true",
        f"--steps={total_steps}",
        MP_FLAG + mp_value(mixed_precision),
    ]


def override(argv: list[str], **flags: str) -> list[str]:
    """Replace (or append) ``--<name>=<value>`` flags; dots in names are written as ``__``."""
    wanted = {f"--{k.replace('__', '.')}=": v for k, v in flags.items()}
    out = [a for a in argv if not any(a.startswith(p) for p in wanted)]
    out += [p + v for p, v in wanted.items()]
    return out
