"""Generate JSON Schema (draft 2020-12) for LeRobot policy / training configs (ADR-5).

Contract: docs/spec/policy-schema.md. Owner of this file: A1 (prototype) -> A4 (BE-Train) maintains.

This module needs LeRobot importable, so it is executed at BUILD time inside an environment that
has the pinned LeRobot (worker image, or the leLab venv on the dev box). The API itself never
imports LeRobot: it serves the generated files in ``api/policy-schemas/*.json``.

Usage::

    env -u PYTHONPATH ~/lelab/leLab/.venv/bin/python backend/app/runs/policy_schema.py \
        --out api/policy-schemas            # write all files
    ... --check                             # exit 1 if committed files are stale (CI)
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import importlib
import inspect
import json
import re
import sys
import types
import typing
from pathlib import Path
from typing import Any

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID_BASE = "https://hibiscus.local/api/policy-schemas/"
GENERATOR_VERSION = "1"

#: policy type -> configuration module (importing it registers the draccus choice).
POLICY_MODULES: dict[str, str] = {
    "act": "lerobot.policies.act.configuration_act",
    "diffusion": "lerobot.policies.diffusion.configuration_diffusion",
    "smolvla": "lerobot.policies.smolvla.configuration_smolvla",
    "vqbet": "lerobot.policies.vqbet.configuration_vqbet",
    "tdmpc": "lerobot.policies.tdmpc.configuration_tdmpc",
    "pi0": "lerobot.policies.pi0.configuration_pi0",
    "pi05": "lerobot.policies.pi05.configuration_pi05",
}

#: Fields of PreTrainedConfig that Hibiscus sets itself and never exposes in the form.
EXCLUDED_FIELDS: dict[str, str] = {
    "input_features": "derived from the dataset version schema by the worker",
    "output_features": "derived from the dataset version schema by the worker",
    "device": "always 'cuda'; the GPU is chosen by the scheduler (CUDA_VISIBLE_DEVICES)",
    "dtype": "torch.dtype is not JSON-serialisable; precision is controlled by train.mixed_precision",
    "use_amp": "deprecated in 0.7.1; use train.mixed_precision (--accelerator.mixed_precision)",
    "use_peft": "set implicitly when train.peft is provided",
    "push_to_hub": "always false; Hub push is a separate Hibiscus action on a model",
    "repo_id": "Hub push is a separate Hibiscus action",
    "private": "Hub push is a separate Hibiscus action",
    "tags": "Hub push is a separate Hibiscus action",
    "license": "Hub push is a separate Hibiscus action",
    "pretrained_path": "set from RunCreate.init_from (model or checkpoint) by the worker",
    "pretrained_revision": "set from RunCreate.init_from by the worker",
    "rtc_config": "inference-time Real-Time-Chunking option, not a training hyperparameter",
    "compile_model": "torch.compile is disabled on the 2-GPU box (P40 unsupported by inductor)",
    "compile_mode": "torch.compile is disabled on the 2-GPU box",
}

#: Curated 'basic' fields per policy (everything else is 'advanced').
BASIC_FIELDS: dict[str, list[str]] = {
    "act": [
        "chunk_size",
        "n_action_steps",
        "use_vae",
        "kl_weight",
        "dim_model",
        "optimizer_lr",
        "vision_backbone",
    ],
    "diffusion": [
        "horizon",
        "n_action_steps",
        "n_obs_steps",
        "noise_scheduler_type",
        "num_inference_steps",
        "crop_shape",
        "optimizer_lr",
    ],
    "smolvla": [
        "chunk_size",
        "n_action_steps",
        "freeze_vision_encoder",
        "train_expert_only",
        "optimizer_lr",
        "vlm_model_name",
        "load_vlm_weights",
    ],
    "vqbet": ["n_obs_steps", "action_chunk_size", "n_vqvae_training_steps", "crop_shape", "optimizer_lr"],
    "tdmpc": ["horizon", "n_action_steps", "use_mpc", "optimizer_lr"],
    "pi0": [
        "chunk_size",
        "n_action_steps",
        "freeze_vision_encoder",
        "train_expert_only",
        "gradient_checkpointing",
        "optimizer_lr",
    ],
    "pi05": [
        "chunk_size",
        "n_action_steps",
        "freeze_vision_encoder",
        "train_expert_only",
        "gradient_checkpointing",
        "optimizer_lr",
    ],
}

#: Constraints that LeRobot enforces in __post_init__ but cannot be read from type hints.
#: Each entry was copied from the 0.7.1 source; keep them in sync when bumping LeRobot.
EXTRA_CONSTRAINTS: dict[str, dict[str, dict[str, Any]]] = {
    "*": {
        "n_action_steps": {"minimum": 1},
        "chunk_size": {"minimum": 1},
        "optimizer_lr": {"exclusiveMinimum": 0},
        "n_obs_steps": {"minimum": 1},
    },
    "act": {
        "vision_backbone": {"pattern": "^resnet"},
        "n_obs_steps": {"const": 1},
        "feedforward_activation": {"enum": ["relu", "gelu", "glu"]},
    },
    "diffusion": {
        "vision_backbone": {"pattern": "^resnet"},
        "noise_scheduler_type": {"enum": ["DDPM", "DDIM"]},
        "prediction_type": {"enum": ["epsilon", "sample"]},
        "crop_ratio": {"exclusiveMinimum": 0, "maximum": 1},
    },
    "vqbet": {"vision_backbone": {"pattern": "^resnet"}},
}

#: Cross-field rules (enforced server-side by A4 in addition to JSON Schema; UI shows them inline).
CROSS_FIELD_RULES: dict[str, list[dict[str, str]]] = {
    "act": [
        {"rule": "n_action_steps <= chunk_size", "code": "policy_config_invalid"},
        {"rule": "temporal_ensemble_coeff == null or n_action_steps == 1", "code": "policy_config_invalid"},
    ],
    "diffusion": [{"rule": "n_action_steps <= horizon - n_obs_steps + 1", "code": "policy_config_invalid"}],
    "smolvla": [{"rule": "n_action_steps <= chunk_size", "code": "policy_config_invalid"}],
    "pi0": [{"rule": "n_action_steps <= chunk_size", "code": "policy_config_invalid"}],
    "pi05": [{"rule": "n_action_steps <= chunk_size", "code": "policy_config_invalid"}],
}

#: Whitelisted TrainPipelineConfig knobs -> (CLI flag, dotted path into the dataclass tree, group).
TRAIN_FIELDS: list[tuple[str, str, str, str]] = [
    ("steps", "--steps", "steps", "basic"),
    ("batch_size", "--batch_size", "batch_size", "basic"),
    ("seed", "--seed", "seed", "advanced"),
    ("num_workers", "--num_workers", "num_workers", "advanced"),
    ("log_freq", "--log_freq", "log_freq", "advanced"),
    ("save_freq", "--save_freq", "save_freq", "basic"),
    ("use_policy_training_preset", "--use_policy_training_preset", "use_policy_training_preset", "advanced"),
    ("cudnn_deterministic", "--cudnn_deterministic", "cudnn_deterministic", "advanced"),
    ("tf32", "--tf32", "tf32", "advanced"),
    ("mixed_precision", "--accelerator.mixed_precision", "accelerator.mixed_precision", "basic"),
    (
        "grad_accum_steps",
        "--accelerator.gradient_accumulation.steps",
        "accelerator.gradient_accumulation.steps",
        "advanced",
    ),
    ("image_transforms", "--dataset.image_transforms.enable", "dataset.image_transforms.enable", "basic"),
]


# ------------------------------------------------------------------------------------------------
# Docstring extraction
# ------------------------------------------------------------------------------------------------
_ARGS_HEADER = re.compile(r"^\s*Args:\s*$")
_ARG_LINE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^)]*\))?:\s*(.*)$")


def _parse_args_section(doc: str | None) -> dict[str, str]:
    """Parse a Google-style ``Args:`` section into {name: text}."""
    if not doc:
        return {}
    out: dict[str, str] = {}
    lines = inspect.cleandoc(doc).splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if _ARGS_HEADER.match(ln))
    except StopIteration:
        return {}
    indent: int | None = None
    current: str | None = None
    for ln in lines[start + 1 :]:
        if not ln.strip():
            continue
        m = _ARG_LINE.match(ln)
        lead = len(ln) - len(ln.lstrip())
        if m and (indent is None or lead == indent):
            indent = lead
            current = m.group(2)
            out[current] = m.group(3).strip()
        elif current is not None and indent is not None and lead > indent:
            out[current] = (out[current] + " " + ln.strip()).strip()
        else:
            break
    return out


def _field_description(cls: type, name: str, args_docs: dict[str, str]) -> str | None:
    if args_docs.get(name):
        return args_docs[name]
    try:
        from draccus.wrappers.docstring import get_attribute_docstring, get_preferred_help_text

        text = get_preferred_help_text(get_attribute_docstring(cls, name), "above")
    except Exception:
        text = None
    if text:
        text = re.sub(r"\s+", " ", text).strip()
        if text.upper().startswith("TODO"):
            return None
    return text or None


# ------------------------------------------------------------------------------------------------
# Type -> JSON Schema
# ------------------------------------------------------------------------------------------------
class UnsupportedTypeError(Exception):
    pass


def _json_default(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return _json_default(value.value)
    if isinstance(value, tuple | list):
        return [_json_default(v) for v in value]
    if isinstance(value, dict):
        return {str(_json_default(k)): _json_default(v) for k, v in value.items()}
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _json_default(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if value is None or isinstance(value, bool | int | float | str):
        return value
    raise UnsupportedTypeError(f"default of type {type(value).__name__}")


def type_to_schema(tp: Any) -> dict[str, Any]:
    """Map a resolved type hint to a JSON Schema fragment."""
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if tp is type(None):
        return {"type": "null"}
    if origin in (typing.Union, types.UnionType):
        non_null = [a for a in args if a is not type(None)]
        has_null = len(non_null) != len(args)
        if len(non_null) == 1:
            inner = type_to_schema(non_null[0])
            if not has_null:
                return inner
            if set(inner) == {"type"} and isinstance(inner["type"], str):
                return {"type": [inner["type"], "null"]}
            return {"anyOf": [inner, {"type": "null"}]}
        branches = [type_to_schema(a) for a in non_null] + ([{"type": "null"}] if has_null else [])
        return {"anyOf": branches}
    if origin is typing.Literal:
        return {"enum": [_json_default(a) for a in args]}
    if tp is bool:
        return {"type": "boolean"}
    if tp is int:
        return {"type": "integer"}
    if tp is float:
        return {"type": "number"}
    if tp is str:
        return {"type": "string"}
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        return {"type": "string", "enum": [_json_default(m) for m in tp]}
    if tp is tuple:
        return {"type": "array"}  # bare `tuple`: element types come from the default value
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return {"type": "array", "items": type_to_schema(args[0])}
        return {
            "type": "array",
            "prefixItems": [type_to_schema(a) for a in args],
            "minItems": len(args),
            "maxItems": len(args),
        }
    if origin is list:
        return {"type": "array", "items": type_to_schema(args[0]) if args else {}}
    if origin is dict:
        key_t, val_t = args if args else (str, Any)
        if key_t is not str:
            raise UnsupportedTypeError(f"dict key {key_t}")
        return {"type": "object", "additionalProperties": type_to_schema(val_t)}
    if dataclasses.is_dataclass(tp) and isinstance(tp, type):
        return dataclass_to_schema(tp, policy=None, exclude=set())[0]
    raise UnsupportedTypeError(repr(tp))


def _refine_bare_tuple(schema: dict[str, Any], default: Any) -> dict[str, Any]:
    if schema.get("type") == "array" and "items" not in schema and "prefixItems" not in schema:
        if isinstance(default, list) and default:
            item_t = "number" if any(isinstance(v, float) for v in default) else "integer"
            schema = {**schema, "items": {"type": item_t}, "minItems": len(default), "maxItems": len(default)}
    return schema


def _coerce_default(schema: dict[str, Any], default: Any) -> Any:
    # e.g. ACT `replace_final_stride_with_dilation: int = False`: LeRobot itself serialises `false`
    # into config.json, so the schema accepts both (schema is widened in place).
    t = schema.get("type")
    if t == "integer" and isinstance(default, bool):
        schema["type"] = ["boolean", "integer"]
        return default
    if t == "number" and isinstance(default, int) and not isinstance(default, bool):
        return float(default)
    return default


def dataclass_to_schema(
    cls: type, *, policy: str | None, exclude: set[str]
) -> tuple[dict[str, Any], dict[str, str]]:
    hints = typing.get_type_hints(cls)
    args_docs: dict[str, str] = {}
    for klass in reversed(inspect.getmro(cls)):
        args_docs.update(_parse_args_section(klass.__doc__))
    props: dict[str, Any] = {}
    skipped: dict[str, str] = {}
    basic = set(BASIC_FIELDS.get(policy or "", []))
    for f in dataclasses.fields(cls):
        if not f.init or f.name.startswith("_"):
            continue
        if f.name in exclude:
            skipped[f.name] = EXCLUDED_FIELDS.get(f.name, "excluded")
            continue
        try:
            schema = type_to_schema(hints[f.name])
            if f.default is not dataclasses.MISSING:
                default = _json_default(f.default)
            elif f.default_factory is not dataclasses.MISSING:
                default = _json_default(f.default_factory())
            else:
                default = dataclasses.MISSING
        except UnsupportedTypeError as exc:
            skipped[f.name] = f"unsupported type: {exc}"
            continue
        if default is not dataclasses.MISSING:
            schema = _refine_bare_tuple(schema, default)
            schema["default"] = _coerce_default(schema, default)
        desc = _field_description(cls, f.name, args_docs)
        if desc:
            schema["description"] = desc
        for scope in ("*", policy or ""):
            schema.update(EXTRA_CONSTRAINTS.get(scope, {}).get(f.name, {}))
        if policy is not None:
            schema["x-hibiscus-group"] = "basic" if f.name in basic else "advanced"
            schema["x-hibiscus-cli"] = f"--policy.{f.name}"
        props[f.name] = schema
    out: dict[str, Any] = {"type": "object", "additionalProperties": False, "properties": props}
    return out, skipped


# ------------------------------------------------------------------------------------------------
# Top-level builders
# ------------------------------------------------------------------------------------------------
def _lerobot_version() -> str:
    import lerobot

    return str(getattr(lerobot, "__version__", "unknown"))


def build_policy_schema(policy_type: str) -> dict[str, Any]:
    from lerobot.configs.policies import PreTrainedConfig

    importlib.import_module(POLICY_MODULES[policy_type])
    cls = PreTrainedConfig.get_choice_class(policy_type)
    body, skipped = dataclass_to_schema(cls, policy=policy_type, exclude=set(EXCLUDED_FIELDS))
    order = BASIC_FIELDS.get(policy_type, [])
    missing = [name for name in order if name not in body["properties"]]
    if missing:
        raise RuntimeError(f"{policy_type}: BASIC_FIELDS not in config: {missing}")
    return {
        "$schema": SCHEMA_DIALECT,
        "$id": f"{SCHEMA_ID_BASE}{policy_type}.json",
        "title": f"{cls.__name__} ({policy_type})",
        "description": (inspect.cleandoc(cls.__doc__ or "").split("\n\n")[0]).strip() or None,
        **body,
        "x-hibiscus": {
            "policy_type": policy_type,
            "config_class": f"{cls.__module__}.{cls.__qualname__}",
            "lerobot_version": _lerobot_version(),
            "generator_version": GENERATOR_VERSION,
            "cli_prefix": "--policy.",
            "basic_order": order,
            "excluded": skipped,
            "cross_field_rules": CROSS_FIELD_RULES.get(policy_type, []),
        },
    }


def _resolve_path(root: type, dotted: str) -> tuple[type, str]:
    cls: Any = root
    parts = dotted.split(".")
    for part in parts[:-1]:
        hints = typing.get_type_hints(cls)
        cls = hints[part]
    return cls, parts[-1]


def build_train_schema() -> dict[str, Any]:
    from lerobot.configs.default import PeftConfig
    from lerobot.configs.train import TrainPipelineConfig

    props: dict[str, Any] = {}
    for name, cli, dotted, group in TRAIN_FIELDS:
        owner, leaf = _resolve_path(TrainPipelineConfig, dotted)
        field = next(f for f in dataclasses.fields(owner) if f.name == leaf)
        schema = type_to_schema(typing.get_type_hints(owner)[leaf])
        if field.default is not dataclasses.MISSING:
            schema["default"] = _json_default(field.default)
        elif field.default_factory is not dataclasses.MISSING:
            schema["default"] = _json_default(field.default_factory())
        desc = _field_description(owner, leaf, _parse_args_section(owner.__doc__))
        if desc:
            schema["description"] = desc
        schema["x-hibiscus-group"] = group
        schema["x-hibiscus-cli"] = cli
        props[name] = schema
    # Hibiscus-specific constraints (resource limits of this box; see docs/spec/policy-schema.md §5).
    props["steps"].update({"minimum": 1, "maximum": 2_000_000})
    props["batch_size"].update({"minimum": 1, "maximum": 512})
    props["num_workers"].update({"minimum": 0, "maximum": 8})
    props["log_freq"].update({"minimum": 10, "maximum": 10_000})
    props["save_freq"].update({"minimum": 100})
    props["grad_accum_steps"].update({"minimum": 1, "maximum": 64})
    props["mixed_precision"].update(
        {
            "enum": ["no", "fp16", "bf16"],
            "description": "Accelerate mixed precision. Forced to 'no' on GPUs "
            "without bf16/fast fp16 (Tesla P40); the run records the effective value.",
        }
    )
    props["steps"]["default"] = 100_000
    props["save_freq"]["default"] = 10_000
    peft_schema, _ = dataclass_to_schema(PeftConfig, policy=None, exclude=set())
    peft_schema["description"] = (
        "PEFT/LoRA adapter config (--peft.*). Required for pi0/pi05 (full fine-tune blocked)."
    )
    peft_schema["x-hibiscus-group"] = "advanced"
    peft_schema["x-hibiscus-cli"] = "--peft."
    props["peft"] = {
        "anyOf": [peft_schema, {"type": "null"}],
        "default": None,
        "x-hibiscus-group": "advanced",
        "x-hibiscus-cli": "--peft.",
    }
    return {
        "$schema": SCHEMA_DIALECT,
        "$id": f"{SCHEMA_ID_BASE}train.json",
        "title": "Hibiscus training options (subset of lerobot TrainPipelineConfig)",
        "type": "object",
        "additionalProperties": False,
        "properties": props,
        "x-hibiscus": {
            "config_class": "lerobot.configs.train.TrainPipelineConfig",
            "lerobot_version": _lerobot_version(),
            "generator_version": GENERATOR_VERSION,
            "managed_by_hibiscus": {
                "--dataset.repo_id": "local/<dataset_version_id>",
                "--dataset.root": "worker-local cache path of the dataset version",
                "--dataset.episodes": "train split episode indices (held-out removed)",
                "--output_dir": "/scratch/runs/<run_id>/output",
                "--job_name": "<run_id>",
                "--trackio.enable": "false",
                "--save_checkpoint": "true",
                "--policy.device": "cuda",
                "--policy.push_to_hub": "false",
            },
        },
    }


def build_all() -> dict[str, dict[str, Any]]:
    out = {f"{p}.json": build_policy_schema(p) for p in POLICY_MODULES}
    out["train.json"] = build_train_schema()
    out["index.json"] = {
        "lerobot_version": _lerobot_version(),
        "generator_version": GENERATOR_VERSION,
        "policies": sorted(POLICY_MODULES),
        "files": sorted(k for k in out if k != "index.json"),
    }
    return out


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=False, ensure_ascii=False, allow_nan=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--out", type=Path, default=Path("api/policy-schemas"))
    ap.add_argument("--check", action="store_true", help="fail if files in --out differ")
    ns = ap.parse_args(argv)
    files = build_all()
    stale: list[str] = []
    ns.out.mkdir(parents=True, exist_ok=True)
    for name, obj in files.items():
        text = _dump(obj)
        path = ns.out / name
        if ns.check:
            if not path.exists() or path.read_text() != text:
                stale.append(name)
        else:
            path.write_text(text)
    if stale:
        print("stale policy schemas: " + ", ".join(stale), file=sys.stderr)
        return 1
    print(f"{'checked' if ns.check else 'wrote'} {len(files)} files in {ns.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
