"""``lerobot-train`` argv builder (policy-schema.md §4 step 5, run-lifecycle §10).

The API stores the argv in ``runs.resolved_args`` with placeholders for worker-local paths; the
worker substitutes them at ``preparing`` and rewrites ``--accelerator.mixed_precision`` with the
effective value for the GPU it runs on (``worker/train/argv.py``).

Value serialisation (draccus parses CLI values as YAML): booleans ``true/false``, ``None`` ->
``null``, lists/dicts -> compact JSON, floats always with a decimal point (``1.0e-05``; YAML 1.1
would read ``1e-05`` as a string), and strings that YAML would re-type (``no``, ``on``, ``1.5``,
``null`` ...) are JSON-quoted (``"no"``). Verified against lerobot-train 0.7.1: unquoted
``--accelerator.mixed_precision=no`` is parsed as ``False`` and rejected; ``"no"`` works both for
fresh runs and for ``--resume=true`` (see docs/handoff/A4-train.md).
"""

from __future__ import annotations

import json
import math
from typing import Any

import yaml

from app.runs.catalog import Catalog

DATASET_ROOT = "{{DATASET_ROOT}}"
OUTPUT_DIR = "{{OUTPUT_DIR}}"
INIT_PATH = "{{INIT_PATH}}"
MAX_NUM_WORKERS = 4


def fmt_float(v: float) -> str:
    if not math.isfinite(v):
        return json.dumps(str(v))
    s = repr(float(v))
    if "e" in s and "." not in s.split("e")[0]:
        mant, exp = s.split("e")
        s = f"{mant}.0e{exp}"
    return s


def fmt_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return fmt_float(v)
    if isinstance(v, str):
        try:
            same = yaml.safe_load(v) == v
        except yaml.YAMLError:
            same = False
        if same and v.strip() == v and v != "":
            return v
        return json.dumps(v)
    if isinstance(v, list | tuple | dict):
        return json.dumps(v, separators=(",", ":"))
    raise TypeError(f"cannot serialise {type(v).__name__} for draccus")


def build_argv(
    cat: Catalog,
    policy_type: str,
    policy: dict[str, Any],
    train: dict[str, Any],
    *,
    run_id: str,
    dataset_repo_id: str,
    train_episodes: list[int],
    has_init_from: bool,
) -> list[str]:
    pschema = cat.policy_schema(policy_type)
    tschema = cat.train_schema
    argv = [
        "lerobot-train",
        f"--policy.type={policy_type}",
        "--policy.device=cuda",
        "--policy.push_to_hub=false",
    ]
    for key in sorted(policy):
        prop = pschema["properties"].get(key)
        if prop is None:
            continue
        if "default" in prop and policy[key] == prop["default"]:
            continue
        argv.append(f"{prop['x-hibiscus-cli']}={fmt_value(policy[key])}")
    if has_init_from:
        argv.append(f"--policy.pretrained_path={INIT_PATH}")
    argv += [
        f"--dataset.repo_id={dataset_repo_id}",
        f"--dataset.root={DATASET_ROOT}",
        f"--dataset.episodes={fmt_value(sorted(train_episodes))}",
        f"--output_dir={OUTPUT_DIR}",
        f"--job_name={run_id}",
    ]
    for key in tschema["properties"]:
        if key not in train:
            continue
        val = train[key]
        if key == "peft":
            if val is None:
                continue
            for sub in sorted(val):
                if val[sub] is not None:
                    argv.append(f"--peft.{sub}={fmt_value(val[sub])}")
            continue
        if key == "num_workers":
            val = min(int(val), MAX_NUM_WORKERS)
        argv.append(f"{tschema['properties'][key]['x-hibiscus-cli']}={fmt_value(val)}")
    argv += ["--save_checkpoint=true", "--trackio.enable=false"]
    return argv
