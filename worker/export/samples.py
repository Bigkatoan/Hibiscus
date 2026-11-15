"""Real dataset samples for parity (docs/spec/bundle.md §6) — decoded once, fed to both runtimes."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from torch import Tensor

from export.policy_info import PolicyInfo


@dataclass
class ParitySamples:
    batches: list[dict[str, Tensor]]  # normalised, batched [1, ...] (history [1, S, ...] if n_obs_steps > 1)
    indices: list[int]  # dataset-relative frame indices
    source: str  # "heldout" | "train"


def open_dataset(
    root: Path,
    repo_id: str,
    episodes: list[int] | None,
    delta_timestamps: dict[str, list[float]] | None = None,
) -> Any:
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    return LeRobotDataset(repo_id, root=root, episodes=episodes, delta_timestamps=delta_timestamps)


def history_delta_timestamps(
    info: PolicyInfo, fps: float, with_history: bool
) -> dict[str, list[float]] | None:
    """Observation history window as LeRobot's training dataloader builds it (oldest first)."""
    if not with_history:
        return None
    deltas = [i / fps for i in range(1 - info.n_obs_steps, 1)]
    keys = [f.key for f in info.input_features if f.type in ("STATE", "VISUAL", "ENV")]
    return dict.fromkeys(keys, deltas)


def load_processors(pretrained_dir: Path, device: str = "cpu") -> tuple[Any, Any]:
    """(preprocessor, postprocessor) exactly as LeRobot inference loads them
    (``make_pre_post_processors`` with the saved pipelines; inputs moved to ``device``, outputs to CPU)."""
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.policies.factory import make_pre_post_processors

    cfg = PreTrainedConfig.from_pretrained(str(pretrained_dir))
    cfg.device = device
    pre, post = make_pre_post_processors(
        cfg,
        pretrained_path=str(pretrained_dir),
        preprocessor_overrides={"device_processor": {"device": device}},
        postprocessor_overrides={"device_processor": {"device": "cpu"}},
    )
    return pre, post


def obs_from_item(item: dict[str, Any], add_batch: bool = True) -> dict[str, Any]:
    obs: dict[str, Any] = {}
    for key, value in item.items():
        if key.startswith("observation.") and not key.endswith("_is_pad"):
            obs[key] = value.unsqueeze(0) if add_batch and isinstance(value, Tensor) else value
    if "task" in item:
        obs["task"] = item["task"]
    return obs


def draw_parity_samples(
    *,
    dataset_root: Path,
    repo_id: str,
    heldout_episodes: list[int],
    info: PolicyInfo,
    preprocessor: Any,
    fps: float,
    n_samples: int = 32,
    seed: int = 0,
) -> ParitySamples:
    """``n_samples`` frames drawn with ``random.Random(seed)`` from held-out episodes (all if none)."""
    with_history = info.policy_type in ("diffusion", "vqbet")
    episodes = sorted(heldout_episodes) if heldout_episodes else None
    ds = open_dataset(dataset_root, repo_id, episodes, history_delta_timestamps(info, fps, with_history))
    rng = random.Random(seed)  # noqa: S311  # reproducible sampling, not crypto
    n = min(n_samples, len(ds))
    indices = sorted(rng.sample(range(len(ds)), n))
    batches: list[dict[str, Tensor]] = []
    keep = {f.key for f in info.input_features}
    for idx in indices:
        item = ds[idx]
        with torch.no_grad():
            out = preprocessor(obs_from_item(item))
        batches.append(
            {k: v.to(torch.float32) for k, v in out.items() if k in keep and isinstance(v, Tensor)}
        )
    return ParitySamples(batches=batches, indices=indices, source="heldout" if episodes else "train")
