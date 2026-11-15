"""Offline held-out evaluation (PLAN §3.5, docs/spec/bundle.md §5) -> ``eval/metrics.json`` + plots.

For every held-out episode the policy is ``reset()`` and fed frames in order through the real
LeRobot pre-processor -> ``select_action`` -> post-processor, so action queues / observation
history behave exactly as in a rollout. Predictions are compared with the recorded ``action`` in
unnormalised joint units. This is an offline error, NOT a success rate on the robot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from export.templates.infer_onnx import Array, normalize

DISCLAIMER_KEY = "eval.offline_not_success_rate"
MAX_EPISODE_PLOTS = 10


@dataclass
class EpisodeTrace:
    episode_index: int
    pred: Array  # [T, A] unnormalised
    gt: Array  # [T, A]


def _normalize_action(x: Array, normalization: dict[str, Any] | None) -> Array | None:
    if not normalization or "action" not in normalization.get("features", {}):
        return None
    return normalize(x, normalization["features"]["action"], float(normalization["eps"]))


def compute_metrics(
    traces: list[EpisodeTrace],
    *,
    action_names: list[str],
    run_id: str,
    step: int,
    normalization: dict[str, Any] | None,
) -> dict[str, Any]:
    """EvalMetrics document (OpenAPI components.schemas.EvalMetrics) from per-episode traces."""
    if not traces:
        raise ValueError("no held-out frames to evaluate")
    pred = np.concatenate([t.pred for t in traces]).astype(np.float64)
    gt = np.concatenate([t.gt for t in traces]).astype(np.float64)
    err = pred - gt
    mae_j = np.abs(err).mean(axis=0)
    mse_j = (err**2).mean(axis=0)
    names = (
        action_names if len(action_names) == pred.shape[1] else [f"joint_{i}" for i in range(pred.shape[1])]
    )
    overall: dict[str, float] = {"mae": float(mae_j.mean()), "mse": float(mse_j.mean())}
    pn = _normalize_action(pred.astype(np.float32), normalization)
    gn = _normalize_action(gt.astype(np.float32), normalization)
    if pn is not None and gn is not None:
        overall["mae_normalized"] = float(np.abs(pn.astype(np.float64) - gn.astype(np.float64)).mean())
    return {
        "schema_version": "1",
        "run_id": run_id,
        "step": int(step),
        "heldout_episodes": [int(t.episode_index) for t in traces],
        "n_frames": int(pred.shape[0]),
        "action_names": list(names),
        "overall": overall,
        "per_joint": [
            {"name": n, "mae": float(a), "mse": float(s)} for n, a, s in zip(names, mae_j, mse_j, strict=True)
        ],
        "plots": [],
        "disclaimer_key": DISCLAIMER_KEY,
    }


def write_plots(
    traces: list[EpisodeTrace], metrics: dict[str, Any], plots_dir: Path, fps: float
) -> list[dict[str, Any]]:
    """``per_joint_mae.png`` + ``episode_<idx:03d>.png`` (pred vs GT per joint, max 10 episodes)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plots_dir.mkdir(parents=True, exist_ok=True)
    names = metrics["action_names"]
    fig, ax = plt.subplots(figsize=(8, 4), dpi=100)
    ax.bar(names, [j["mae"] for j in metrics["per_joint"]], color="#3b6ea8")
    ax.set_ylabel("MAE (joint units)")
    ax.set_title(f"Held-out MAE per joint — step {metrics['step']} (offline, not a success rate)")
    ax.tick_params(axis="x", labelrotation=30)
    fig.tight_layout()
    fig.savefig(plots_dir / "per_joint_mae.png")
    plt.close(fig)

    entries: list[dict[str, Any]] = []
    for tr in traces[:MAX_EPISODE_PLOTS]:
        n = tr.pred.shape[1]
        cols = 2 if n > 1 else 1
        rows = (n + cols - 1) // cols
        fig, axes = plt.subplots(rows, cols, figsize=(11, 2.4 * rows), dpi=90, squeeze=False, sharex=True)
        t = np.arange(tr.pred.shape[0]) / fps
        for j in range(rows * cols):
            a = axes[j // cols][j % cols]
            if j >= n:
                a.axis("off")
                continue
            a.plot(t, tr.gt[:, j], label="recorded", color="#444444", linewidth=1.2)
            a.plot(t, tr.pred[:, j], label="predicted", color="#d9822b", linewidth=1.0)
            a.set_title(names[j] if j < len(names) else f"joint_{j}", fontsize=9)
            a.grid(alpha=0.3)
        axes[0][0].legend(fontsize=8, loc="best")
        for a in axes[-1]:
            a.set_xlabel("time (s)")
        fig.suptitle(f"Episode {tr.episode_index}: predicted vs recorded action (step {metrics['step']})")
        fig.tight_layout()
        name = f"episode_{tr.episode_index:03d}.png"
        fig.savefig(plots_dir / name)
        plt.close(fig)
        entries.append({"episode_index": int(tr.episode_index), "path": f"eval/plots/{name}"})
    return entries


def rollout_episode(policy: Any, pre: Any, post: Any, dataset: Any, device: str) -> EpisodeTrace:
    """select_action over one episode's frames in order (dataset already filtered to the episode)."""
    import torch

    from export.samples import obs_from_item

    policy.reset()
    preds: list[Array] = []
    gts: list[Array] = []
    episode_index = -1
    # Sequential, in-process decoding: forked DataLoader workers inherit torchcodec decoder state
    # from the parent (parity sampling opened it) and fail with "Could not push packet to decoder".
    with torch.inference_mode():
        for i in range(len(dataset)):
            item = dataset[i]
            episode_index = int(item["episode_index"])
            batch = pre(obs_from_item(item))
            action = post(policy.select_action(batch))
            preds.append(action.reshape(-1).float().cpu().numpy())
            gts.append(item["action"].reshape(-1).float().cpu().numpy())
    return EpisodeTrace(episode_index=episode_index, pred=np.stack(preds), gt=np.stack(gts))


def evaluate_heldout(
    *,
    pretrained_dir: Path,
    dataset_root: Path,
    repo_id: str,
    heldout_episodes: list[int],
    run_id: str,
    step: int,
    out_dir: Path | None = None,
    device: str = "cpu",
    policy: Any = None,
) -> dict[str, Any]:
    """Evaluate one checkpoint on held-out episodes.

    ``out_dir`` = the bundle's ``eval/`` directory: writes ``metrics.json`` and ``plots/``.
    ``out_dir=None`` only computes the metrics (per-checkpoint evaluation during training).
    """
    import torch

    from export.normalization import build_normalization
    from export.onnx_export import load_policy_cpu
    from export.policy_info import load_policy_info
    from export.samples import load_processors, open_dataset

    if not heldout_episodes:
        raise ValueError("no held-out episodes")
    info = load_policy_info(pretrained_dir)
    if policy is None:
        policy = load_policy_cpu(pretrained_dir, info.policy_type)
    policy.to(device)
    policy.config.device = device
    pre, post = load_processors(pretrained_dir, device)
    torch.manual_seed(0)
    try:
        normalization: dict[str, Any] | None = build_normalization(pretrained_dir, info)
    except ValueError:
        normalization = None
    traces: list[EpisodeTrace] = []
    meta_names: list[str] = []
    fps = 30.0
    for ep in sorted(heldout_episodes):
        ds = open_dataset(dataset_root, repo_id, [ep])
        fps = float(ds.fps)
        meta_names = list(ds.meta.features["action"].get("names") or [])
        traces.append(rollout_episode(policy, pre, post, ds, device))
    metrics = compute_metrics(
        traces, action_names=meta_names, run_id=run_id, step=step, normalization=normalization
    )
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        metrics["plots"] = write_plots(traces, metrics, out_dir / "plots", fps)
        (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    policy.to("cpu")
    policy.config.device = "cpu"
    return metrics
