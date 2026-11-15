"""Load exported bundles with the LeLab venv's LeRobot exactly like LeLab would (owner: A10).

Usage: <lelab-venv>/bin/python -I lelab_load_check.py BUNDLE_DIR [BUNDLE_DIR ...]
Each BUNDLE_DIR contains pretrained_model/. Exit 0 only if every bundle loads and produces an
action of the dataset's action dimension from a dummy observation built from the config.
"""

from __future__ import annotations

import importlib.metadata as md
import sys
from pathlib import Path

import torch
from lerobot.policies.factory import get_policy_class, make_pre_post_processors
from lerobot.configs.policies import PreTrainedConfig


def check(bundle: Path) -> None:
    pm = bundle / "pretrained_model"
    cfg = PreTrainedConfig.from_pretrained(pm)
    policy = get_policy_class(cfg.type).from_pretrained(pm)
    policy.eval()
    pre, post = make_pre_post_processors(policy.config, pretrained_path=str(pm))
    obs: dict[str, object] = {"task": ["Pick the blue cube and place on top the white cube"]}
    for key, feat in policy.config.input_features.items():
        obs[key] = torch.rand(1, *feat.shape) if "image" in key else torch.zeros(1, *feat.shape)
    with torch.no_grad():
        action = post(policy.select_action(pre(obs)))
    want = next(iter(policy.config.output_features.values())).shape
    assert tuple(action.shape[-1:]) == tuple(want[-1:]), (action.shape, want)
    print(f"OK {bundle.name}: {cfg.type} action {tuple(action.shape)} inputs {list(policy.config.input_features)}")


def main(argv: list[str]) -> int:
    print(f"lerobot {md.version('lerobot')} torch {torch.__version__}")
    bad = 0
    for arg in argv:
        try:
            check(Path(arg))
        except Exception as e:  # noqa: BLE001 - report every bundle
            bad += 1
            print(f"FAIL {arg}: {type(e).__name__}: {e}")
    return 1 if bad or not argv else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
