"""Write trusted ``policy_preprocessor.json`` / ``policy_postprocessor.json`` into a policy dir.

SEC-input-1: processor JSON files of an ``init_from.hf_repo_id`` repo are never downloaded. This
script rebuilds them from LeRobot's own factory for the policy type in ``config.json`` and the
run's dataset statistics, then saves them next to the weights, so ``lerobot-train
--policy.pretrained_path=<dir>`` loads processors Hibiscus generated. (lerobot-train replaces the
normalizer statistics with the dataset's anyway when it does not resume.)

Runs in a FRESH interpreter (``python -I trusted_processors.py ...``) with the allow-listed child
env, so nothing from the repo is ever parsed inside the worker process. Prints one JSON line.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _generate(args: argparse.Namespace) -> dict[str, Any]:  # pragma: no cover - runs in a subprocess
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.datasets.lerobot_dataset import LeRobotDatasetMetadata
    from lerobot.policies.factory import make_pre_post_processors

    policy_dir = Path(args.policy_dir)
    for name in ("policy_preprocessor.json", "policy_postprocessor.json"):
        (policy_dir / name).unlink(missing_ok=True)
    for f in policy_dir.glob("policy_*processor_step_*.safetensors"):
        f.unlink()
    cfg = PreTrainedConfig.from_pretrained(str(policy_dir))
    meta = LeRobotDatasetMetadata(args.repo_id, root=args.dataset_root)
    pre, post = make_pre_post_processors(cfg, dataset_stats=meta.stats)
    pre.save_pretrained(str(policy_dir))
    post.save_pretrained(str(policy_dir))
    return {"ok": True, "policy_type": cfg.type, "files": sorted(p.name for p in policy_dir.iterdir())}


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - runs in a subprocess
    parser = argparse.ArgumentParser(description="Hibiscus trusted processor generator")
    parser.add_argument("--policy-dir", required=True)
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--repo-id", required=True)
    args = parser.parse_args(argv)
    try:
        result = _generate(args)
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
