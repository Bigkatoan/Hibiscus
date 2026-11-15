"""Policy catalogue served from ``api/policy-schemas`` (no LeRobot import, CONTRACT_NOTES D5)."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.runs.settings import get_runs_settings

POLICY_TYPES = ("act", "diffusion", "vqbet", "tdmpc", "smolvla", "pi0", "pi05")


@dataclass(frozen=True, slots=True)
class PolicyMeta:
    display_name: str
    onnx: str  # full | split | none
    onnx_reason_key: str | None
    requires_peft: bool
    requires_reward: bool
    requires_language: bool
    experimental: bool
    #: Minimum GPU VRAM (MiB) for the policy to be eligible at all (run-lifecycle §7.4).
    min_vram_mb: int
    #: Below this VRAM the policy is "limited" (bs small) rather than "supported".
    comfortable_vram_mb: int


# PLAN §3.3 matrix + run-lifecycle §7.4 + CONTRACT_NOTES D11.
POLICY_META: dict[str, PolicyMeta] = {
    "act": PolicyMeta("ACT", "full", None, False, False, False, False, 0, 0),
    "diffusion": PolicyMeta("Diffusion Policy", "split", None, False, False, False, False, 0, 0),
    "vqbet": PolicyMeta("VQ-BeT", "full", None, False, False, False, False, 0, 0),
    "tdmpc": PolicyMeta("TD-MPC", "none", "onnx.reason.tdmpc_v1", False, True, False, False, 0, 0),
    "smolvla": PolicyMeta(
        "SmolVLA", "none", "onnx.reason.vla_tokenizer", False, False, True, False, 0, 16000
    ),
    "pi0": PolicyMeta("π0", "none", "onnx.reason.vla_tokenizer", True, False, True, True, 20000, 10**9),
    "pi05": PolicyMeta("π0.5", "none", "onnx.reason.vla_tokenizer", True, False, True, True, 20000, 10**9),
}


def gpu_support_level(policy_type: str, total_vram_mb: int) -> str:
    meta = POLICY_META[policy_type]
    if total_vram_mb < meta.min_vram_mb:
        return "unsupported"
    if total_vram_mb < meta.comfortable_vram_mb:
        return "limited"
    return "supported"


def unsupported_policies_for_vram(total_vram_mb: int) -> list[str]:
    return [p for p in POLICY_TYPES if gpu_support_level(p, total_vram_mb) == "unsupported"]


@dataclass(frozen=True)
class Catalog:
    lerobot_version: str
    schemas: dict[str, dict[str, Any]]
    train_schema: dict[str, Any]
    presets: list[dict[str, Any]]
    etags: dict[str, str]

    def policy_schema(self, policy_type: str) -> dict[str, Any]:
        return self.schemas[policy_type]

    def defaults(self, schema: dict[str, Any]) -> dict[str, Any]:
        return {k: copy.deepcopy(v["default"]) for k, v in schema["properties"].items() if "default" in v}

    def presets_for(self, policy_type: str) -> list[dict[str, Any]]:
        """Presets with ``per_policy[type]`` folded in (OpenAPI ``Preset``)."""
        out = []
        for p in self.presets:
            per = p.get("per_policy", {}).get(policy_type, {})
            out.append(
                {
                    "id": p["id"],
                    "label_key": p["label_key"],
                    "requires_init_from": bool(p.get("requires_init_from", False)),
                    "train": {**p.get("train", {}), **per.get("train", {})},
                    "policy": {**p.get("policy", {}), **per.get("policy", {})},
                }
            )
        return out

    def preset(self, policy_type: str, preset_id: str) -> dict[str, Any] | None:
        for p in self.presets_for(policy_type):
            if p["id"] == preset_id:
                return p
        return None


def _etag(*docs: Any) -> str:
    h = hashlib.sha256()
    for d in docs:
        h.update(json.dumps(d, sort_keys=True, separators=(",", ":")).encode())
    return '"' + h.hexdigest()[:32] + '"'


def load_catalog(directory: Path) -> Catalog:
    index = json.loads((directory / "index.json").read_text())
    schemas = {p: json.loads((directory / f"{p}.json").read_text()) for p in index["policies"]}
    train = json.loads((directory / "train.json").read_text())
    presets = json.loads((directory / "presets.json").read_text())["presets"]
    etags = {p: _etag(schemas[p], train, presets) for p in schemas}
    return Catalog(index["lerobot_version"], schemas, train, presets, etags)


@lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    return load_catalog(get_runs_settings().policy_schemas_dir)


def summary(cat: Catalog, policy_type: str, gpus: list[tuple[str, int]]) -> dict[str, Any]:
    meta = POLICY_META[policy_type]
    return {
        "type": policy_type,
        "display_name": meta.display_name,
        "trainable": True,
        "onnx": meta.onnx,
        "onnx_reason_key": meta.onnx_reason_key,
        "requires_peft": meta.requires_peft,
        "requires_reward": meta.requires_reward,
        "requires_language": meta.requires_language,
        "gpu_support": {name: gpu_support_level(policy_type, vram) for name, vram in gpus},
        "schema_etag": cat.etags[policy_type],
        "experimental": meta.experimental,
    }
