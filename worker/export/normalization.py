"""Build ``onnx/normalization.json`` (docs/spec/bundle.md §4.3) from the processor state files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from safetensors.numpy import load_file

from export.policy_info import PolicyInfo

STATS_FOR_MODE: dict[str, tuple[str, ...]] = {
    "MEAN_STD": ("mean", "std"),
    "MIN_MAX": ("min", "max"),
    "QUANTILES": ("q01", "q99"),
    "QUANTILE10": ("q10", "q90"),
    "IDENTITY": (),
}
ALLOWED_TYPES = ("STATE", "VISUAL", "ACTION", "ENV")


class NormalizationError(ValueError):
    pass


def _find_step(pipeline_json: Path, registry_name: str) -> dict[str, Any]:
    doc = json.loads(pipeline_json.read_text())
    for step in doc.get("steps", []):
        if step.get("registry_name") == registry_name:
            return dict(step)
    raise NormalizationError(f"{pipeline_json.name}: no '{registry_name}' step")


def _stats_from_step(pretrained_dir: Path, step: dict[str, Any]) -> dict[str, NDArray[np.float32]]:
    state_file = step.get("state_file")
    if not state_file:
        return {}
    return dict(load_file(str(pretrained_dir / state_file)))


def _as_list(arr: NDArray[np.float32]) -> list[float]:
    # float(np.float32(v)): exact float32 value, no rounding (spec §4.3)
    return [float(np.float32(v)) for v in np.asarray(arr, dtype=np.float32).reshape(-1)]


def build_normalization(pretrained_dir: Path, info: PolicyInfo) -> dict[str, Any]:
    """Return the normalization.json document for the features the policy normalises."""
    pre = _find_step(pretrained_dir / "policy_preprocessor.json", "normalizer_processor")
    post = _find_step(pretrained_dir / "policy_postprocessor.json", "unnormalizer_processor")
    pre_stats = _stats_from_step(pretrained_dir, pre)
    post_stats = _stats_from_step(pretrained_dir, post)
    eps = float(pre.get("config", {}).get("eps", 1e-8))
    pre_norm_map: dict[str, str] = dict(pre.get("config", {}).get("norm_map") or info.normalization_mapping)
    post_norm_map: dict[str, str] = dict(post.get("config", {}).get("norm_map") or info.normalization_mapping)

    features: dict[str, Any] = {}
    for feat in (*info.input_features, *info.output_features):
        if feat.type not in ALLOWED_TYPES:
            continue
        is_action = feat.type == "ACTION"
        norm_map = post_norm_map if is_action else pre_norm_map
        stats = post_stats if is_action else pre_stats
        mode = str(norm_map.get(feat.type, "IDENTITY"))
        if mode not in STATS_FOR_MODE:
            raise NormalizationError(f"{feat.key}: unsupported normalisation mode {mode!r}")
        entry: dict[str, Any] = {"type": feat.type, "mode": mode}
        for stat in STATS_FOR_MODE[mode]:
            name = f"{feat.key}.{stat}"
            if name not in stats:
                raise NormalizationError(
                    f"{feat.key}: mode {mode} needs '{stat}' but the state file lacks {name}"
                )
            entry[stat] = _as_list(stats[name])
        features[feat.key] = entry
    return {"schema_version": "1", "eps": eps, "features": features}
