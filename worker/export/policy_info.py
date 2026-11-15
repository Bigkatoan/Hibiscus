"""Static facts about a LeRobot checkpoint, read from ``pretrained_model/config.json`` only.

No torch / lerobot import: usable by the API-side and by lightweight tooling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

PolicyType = Literal["act", "diffusion", "vqbet", "tdmpc", "smolvla", "pi0", "pi05"]
OnnxSupport = Literal["full", "split", "none"]

#: docs/spec/bundle.md §11 policy support matrix.
ONNX_SUPPORT: dict[str, OnnxSupport] = {
    "act": "full",
    "vqbet": "full",
    "diffusion": "split",
    "tdmpc": "none",
    "smolvla": "none",
    "pi0": "none",
    "pi05": "none",
}

STATE_KEY = "observation.state"
ENV_KEY = "observation.environment_state"
IMAGE_PREFIX = "observation.images."
ACTION_KEY = "action"


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    type: str  # STATE | VISUAL | ACTION | ENV
    shape: tuple[int, ...]


@dataclass(frozen=True)
class PolicyInfo:
    """Subset of the policy config needed by export, io_spec, manifest and run_on_robot.sh."""

    policy_type: str
    input_features: tuple[FeatureSpec, ...]
    output_features: tuple[FeatureSpec, ...]
    normalization_mapping: dict[str, str]
    n_obs_steps: int
    chunk_size: int | None
    n_action_steps: int | None
    raw: dict[str, Any]

    @property
    def onnx_support(self) -> OnnxSupport:
        return ONNX_SUPPORT.get(self.policy_type, "none")

    @property
    def image_keys(self) -> list[str]:
        """Camera keys in ``input_features`` insertion order (= graph input order)."""
        return [f.key for f in self.input_features if f.type == "VISUAL"]

    def feature(self, key: str) -> FeatureSpec | None:
        for f in (*self.input_features, *self.output_features):
            if f.key == key:
                return f
        return None

    def require_feature(self, key: str) -> FeatureSpec:
        feat = self.feature(key)
        if feat is None:
            raise KeyError(f"feature {key!r} not in the policy config")
        return feat

    @property
    def state(self) -> FeatureSpec | None:
        return next((f for f in self.input_features if f.type == "STATE"), None)

    @property
    def env_state(self) -> FeatureSpec | None:
        return next((f for f in self.input_features if f.type == "ENV"), None)

    @property
    def action(self) -> FeatureSpec:
        act = next((f for f in self.output_features if f.type == "ACTION"), None)
        if act is None:
            raise ValueError("policy config has no ACTION output feature")
        return act

    @property
    def peft(self) -> dict[str, Any] | None:
        if not self.raw.get("use_peft"):
            return None
        peft = self.raw.get("peft_config") or self.raw.get("peft")
        return peft if isinstance(peft, dict) else {"enabled": True}


def _features(raw: dict[str, Any]) -> tuple[FeatureSpec, ...]:
    return tuple(
        FeatureSpec(key=k, type=str(v["type"]), shape=tuple(int(s) for s in v["shape"]))
        for k, v in raw.items()
    )


def chunk_and_steps(cfg: dict[str, Any]) -> tuple[int | None, int | None]:
    """(chunk_size, n_action_steps) per MANIFEST.policy description."""
    ptype = cfg["type"]
    if ptype == "diffusion":
        return int(cfg["horizon"]), int(cfg["n_action_steps"])
    if ptype == "vqbet":
        n = int(cfg["action_chunk_size"])
        return n, n
    if ptype == "tdmpc":
        return int(cfg["horizon"]), int(cfg.get("n_action_steps") or 1)
    chunk = cfg.get("chunk_size")
    steps = cfg.get("n_action_steps")
    return (int(chunk) if chunk else None), (int(steps) if steps else None)


def load_policy_info(pretrained_dir: Path) -> PolicyInfo:
    raw: dict[str, Any] = json.loads((pretrained_dir / "config.json").read_text())
    chunk, steps = chunk_and_steps(raw)
    return PolicyInfo(
        policy_type=str(raw["type"]),
        input_features=_features(raw.get("input_features") or {}),
        output_features=_features(raw.get("output_features") or {}),
        normalization_mapping={str(k): str(v) for k, v in (raw.get("normalization_mapping") or {}).items()},
        n_obs_steps=int(raw.get("n_obs_steps") or 1),
        chunk_size=chunk,
        n_action_steps=steps,
        raw=raw,
    )
