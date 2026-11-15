"""``MODEL_CARD.md`` (docs/spec/bundle.md §9) and its Hugging Face ``README.md`` variant."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from export.lelab_compat import pip_command

_SKIP_KEYS = {
    "input_features",
    "output_features",
    "device",
    "push_to_hub",
    "repo_id",
    "private",
    "tags",
    "license",
    "pretrained_path",
    "pretrained_revision",
    "type",
}


@dataclass
class CardContext:
    bundle_name: str
    policy_type: str
    dataset_name: str
    dataset_version: int
    dataset_repo_id: str
    dataset_content_hash: str
    checkpoint_step: int
    verified: bool
    load_ok: bool
    parity_ok: bool | None
    onnx_status: str
    onnx_support: str
    run_name: str
    run_number: int
    seed: int
    total_steps: int
    batch_size: int
    mixed_precision: str
    gpu_name: str
    gpu_seconds: float
    heldout_episodes: list[int]
    train_episodes: list[int]
    final_loss: float | None
    software: dict[str, Any]
    config: dict[str, Any]
    config_defaults: dict[str, Any] | None
    eval_metrics: dict[str, Any] | None
    parity_report: dict[str, Any] | None
    fps: float
    tasks: list[str] = field(default_factory=list)
    #: QC-ml-1: does the bundle load in the LeLab venv without extra packages?
    lelab_compatible: bool = True
    #: "lelab_venv" (checked with a LeLab interpreter) or "emulated" (worker Python, extras hidden).
    lelab_check: str = "emulated"
    #: pip requirements to install inside the LeLab venv first (empty when none are needed).
    lelab_requirements: list[str] = field(default_factory=list)


def episode_ranges(episodes: list[int]) -> str:
    """``[0, 1, 2, 5, 7, 8]`` -> ``"0-2, 5, 7-8"``."""
    eps = sorted(set(int(e) for e in episodes))
    parts: list[str] = []
    i = 0
    while i < len(eps):
        j = i
        while j + 1 < len(eps) and eps[j + 1] == eps[j] + 1:
            j += 1
        parts.append(str(eps[i]) if i == j else f"{eps[i]}-{eps[j]}")
        i = j + 1
    return ", ".join(parts)


def split_row(train: list[int], heldout: list[int]) -> str:
    """QC-ml-3: counts and episode indices side by side, so no number reads as an episode index."""

    def one(label: str, eps: list[int]) -> str:
        n = len(set(eps))
        noun = "episode" if n == 1 else "episodes"
        return f"{label}: {n} {noun} ({episode_ranges(eps)})" if n else f"{label}: none"

    return f"{one('train', train)}, {one('held-out', heldout)}"


def config_diff(config: dict[str, Any], defaults: dict[str, Any] | None) -> list[tuple[str, Any, Any]]:
    """(key, value, default) for every policy hyper-parameter that differs from the LeRobot default."""
    rows: list[tuple[str, Any, Any]] = []
    for key in sorted(config):
        if key in _SKIP_KEYS:
            continue
        value = config[key]
        default = (defaults or {}).get(key, "—")
        if defaults is None or _norm(value) != _norm(default):
            rows.append((key, value, default))
    return rows


def _norm(v: Any) -> str:
    return json.dumps(v, sort_keys=True, default=str)


def _fmt(v: Any) -> str:
    s = json.dumps(v, default=str) if not isinstance(v, str) else v
    s = s.replace("|", "\\|")
    return s if len(s) <= 80 else s[:77] + "..."


def _duration(seconds: float) -> str:
    s = round(seconds)
    return f"{s // 3600}h {s % 3600 // 60:02d}m {s % 60:02d}s"


def render_model_card(ctx: CardContext) -> str:
    badge = "verified" if ctx.verified else "not verified"
    parity = {True: "passed", False: "FAILED", None: "n/a"}[ctx.parity_ok]
    how = (
        "checked with the LeLab interpreter"
        if ctx.lelab_check == "lelab_venv"
        else ("checked with LeLab's missing packages hidden")
    )
    if ctx.lelab_compatible:
        lelab = f"ok ({how})"
    elif ctx.lelab_requirements:
        lelab = f"**needs extra packages** ({how}): `{pip_command(ctx.lelab_requirements)}`"
    else:
        lelab = f"**FAILED** ({how})"
    lines: list[str] = [
        f"# {ctx.bundle_name}",
        "",
        "## Summary",
        "_Tóm tắt_",
        "",
        "| | |",
        "|---|---|",
        f"| Policy | `{ctx.policy_type}` (ONNX support: {ctx.onnx_support}) |",
        f"| Dataset | `{ctx.dataset_name}` @ v{ctx.dataset_version} (`{ctx.dataset_repo_id}`) |",
        f"| Checkpoint step | {ctx.checkpoint_step} |",
        f"| Status | **{badge}** — LeRobot 0.7.1 load: {'ok' if ctx.load_ok else 'FAILED'}, "
        f"LeLab venv: {lelab}, "
        f"ONNX: {ctx.onnx_status}, parity: {parity}, MANIFEST hashes: checked on the downloaded zip |",
        f"| Run | {ctx.run_name} (#{ctx.run_number}) |",
        "",
        "## Intended use & limitations",
        "_Mục đích sử dụng & giới hạn_",
        "",
        f"Imitation-learning policy for the task(s): {', '.join(repr(t) for t in ctx.tasks) or 'n/a'}, "
        "trained on the dataset above for the same robot and camera setup. Offline evaluation measures the "
        "error between predicted and recorded actions on held-out episodes; "
        "**it is not a success rate on the real robot**. "
        "Validate on hardware with a hand on the emergency stop.",
        "",
        "Đánh giá offline đo sai số giữa action dự đoán và action đã ghi trên các episode held-out; "
        "**đây không phải tỉ lệ thành công trên robot thật**.",
        "",
        "## Training",
        "_Huấn luyện_",
        "",
        "| | |",
        "|---|---|",
        f"| Steps | {ctx.total_steps} (this checkpoint: {ctx.checkpoint_step}) |",
        f"| Batch size | {ctx.batch_size} |",
        f"| Seed | {ctx.seed} |",
        f"| Mixed precision | {ctx.mixed_precision} |",
        f"| GPU | {ctx.gpu_name} |",
        f"| GPU time | {_duration(ctx.gpu_seconds)} |",
        f"| Split | {split_row(ctx.train_episodes, ctx.heldout_episodes)} |",
        "",
        "Hyper-parameters that differ from the LeRobot defaults (resolved policy config):",
        "",
        "| key | value | default |",
        "|---|---|---|",
    ]
    diff = config_diff(ctx.config, ctx.config_defaults)
    lines += [f"| `{k}` | {_fmt(v)} | {_fmt(d)} |" for k, v, d in diff] or ["| — | (all defaults) | |"]
    lines += ["", "## Results", "_Kết quả_", ""]
    lines.append(
        f"Final training loss: {ctx.final_loss:.4f}" if ctx.final_loss is not None else "Final loss: n/a"
    )
    lines.append("")
    if ctx.eval_metrics:
        m = ctx.eval_metrics
        lines += [
            f"Offline eval on held-out episodes {m['heldout_episodes']} ({m['n_frames']} frames), "
            "unnormalised joint units:",
            "",
            "| joint | MAE | MSE |",
            "|---|---|---|",
        ]
        lines += [f"| {j['name']} | {j['mae']:.4f} | {j['mse']:.4f} |" for j in m["per_joint"]]
        lines.append(f"| **overall** | **{m['overall']['mae']:.4f}** | **{m['overall']['mse']:.4f}** |")
        lines += ["", "Plots: `eval/plots/per_joint_mae.png`, `eval/plots/episode_<idx>.png`."]
    else:
        lines.append("No offline evaluation (no held-out episodes or eval disabled).")
    if ctx.parity_report:
        lines += [
            "",
            "ONNX parity (onnxruntime CPU vs PyTorch CPU, normalised outputs):",
            "",
            "| comparison | max abs diff | atol | passed | gating |",
            "|---|---|---|---|---|",
        ]
        for g in ctx.parity_report["graphs"]:
            cells = [g["comparison"], f"{g['max_abs_diff']:.3g}", f"{g['atol']:g}", g["passed"], g["gating"]]
            lines.append("| " + " | ".join(str(c) for c in cells) + " |")
    lines += [
        "",
        "## How to run",
        "_Cách chạy_",
        "",
        "LeRobot (inside the LeLab venv):",
        "",
        "```bash",
        "source ~/lelab/leLab/.venv/bin/activate",
    ]
    if ctx.lelab_requirements:
        lines.append(
            f"{pip_command(ctx.lelab_requirements)}   # once: `{ctx.policy_type}` needs these packages, "
            "which the LeLab venv does not have"
        )
    elif not ctx.lelab_compatible:
        lines.append("# WARNING: this bundle did not load in the LeLab venv; see Status above")
    lines += [
        "PORT=/dev/ttyACM0 ./run_on_robot.sh          # wraps lerobot-rollout --policy.path=pretrained_model",
        "```",
        "",
        "Any LeRobot command accepts `--policy.path=<bundle>/pretrained_model`.",
    ]
    if ctx.onnx_status in ("passed", "failed"):
        lines += [
            "",
            "ONNX without LeRobot (`pip install -r onnx/requirements.txt`):",
            "",
            "```bash",
            "python onnx/infer_onnx.py --bundle . --selftest",
            "```",
        ]
    lines += [
        "",
        "Download with the CLI: `hibiscus pull <model>`.",
        "",
        "## Reproducibility",
        "_Khả năng tái lập_",
        "",
        "| | |",
        "|---|---|",
        f"| LeRobot | {ctx.software.get('lerobot')} |",
        f"| torch | {ctx.software.get('torch')} (CUDA {ctx.software.get('cuda')}) |",
        f"| Python | {ctx.software.get('python')} |",
        f"| onnx / onnxruntime | {ctx.software.get('onnx')} / {ctx.software.get('onnxruntime')} |",
        f"| Worker image | `{ctx.software.get('image_digest')}` |",
        f"| Dataset content hash | `{ctx.dataset_content_hash}` |",
        f"| fps | {ctx.fps:g} |",
        "",
        "## Files",
        "_Tệp_",
        "",
        "Every file with its size and sha256 is listed in [`MANIFEST.json`](MANIFEST.json).",
        "",
    ]
    return "\n".join(lines)


def hub_readme(card_md: str, *, policy_type: str, dataset_repo_id: str | None) -> str:
    """Model card with Hugging Face YAML front matter (README.md for Hub pushes)."""
    front = ["---", "library_name: lerobot", "tags:", "- lerobot", f"- {policy_type}", "- robotics"]
    if dataset_repo_id:
        front += ["datasets:", f"- {dataset_repo_id}"]
    front.append("---")
    return "\n".join(front) + "\n\n" + card_md
