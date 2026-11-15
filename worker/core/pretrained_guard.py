"""Checks on a LeRobot ``pretrained_model`` directory before LeRobot loads it (SEC-input-1).

LeRobot's ``DataProcessorPipeline.from_pretrained`` imports the dotted path in a step's ``"class"``
key and calls it with the step's ``"config"`` BEFORE it checks that the result is a ProcessorStep.
A processor JSON from an untrusted source is therefore code execution
(``{"class": "subprocess.Popen", "config": {"args": [...]}}``).

:func:`validate_pretrained_dir` rejects every processor JSON in the directory unless each step:

* names its class by ``registry_name`` (never ``"class"``), and the name is in
  :data:`ALLOWED_PROCESSOR_STEPS`: the ``lerobot.processor`` steps that the policies Hibiscus
  trains (act, diffusion, vqbet, tdmpc, smolvla, pi0, pi05) save in LeRobot 0.7.1;
* uses only the keys ``registry_name``, ``config`` and ``state_file``, and a ``state_file`` that is
  a plain ``*.safetensors`` file name in the same directory.

It also checks that ``config.json`` is a JSON object whose ``type`` is a known policy type.
Stdlib only, so it can run anywhere (worker, export, tests).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

#: Registry names of LeRobot 0.7.1 processor steps used by the trainable policies (all defined in
#: ``lerobot.processor.*``). Anything else is rejected, including other registered steps.
ALLOWED_PROCESSOR_STEPS = frozenset(
    {
        "rename_observations_processor",
        "to_batch_processor",
        "device_processor",
        "normalizer_processor",
        "unnormalizer_processor",
        "tokenizer_processor",
        "smolvla_new_line_processor",
        "pi0_new_line_processor",
        "pi05_prepare_state_tokenizer_processor_step",
        "relative_actions_processor",
        "absolute_actions_processor",
    }
)
POLICY_TYPES = frozenset({"act", "diffusion", "vqbet", "tdmpc", "smolvla", "pi0", "pi05"})
PROCESSOR_FILES = ("policy_preprocessor.json", "policy_postprocessor.json")
_STEP_KEYS = frozenset({"registry_name", "config", "state_file"})
_STATE_FILE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,200}\.safetensors$")
_MAX_JSON_BYTES = 8 * 1024 * 1024


class UntrustedPretrainedError(ValueError):
    """The directory contains something LeRobot must not load."""


def validate_processor_config(doc: Any, *, source: str = "processor") -> None:
    if not isinstance(doc, dict):
        raise UntrustedPretrainedError(f"{source}: not a JSON object")
    steps = doc.get("steps")
    if not isinstance(steps, list):
        raise UntrustedPretrainedError(f"{source}: 'steps' must be a list")
    for i, step in enumerate(steps):
        where = f"{source} step {i}"
        if not isinstance(step, dict):
            raise UntrustedPretrainedError(f"{where}: not an object")
        if "class" in step:
            raise UntrustedPretrainedError(
                f"{where}: 'class' import paths are not allowed (got {str(step['class'])[:120]!r})"
            )
        extra = set(step) - _STEP_KEYS
        if extra:
            raise UntrustedPretrainedError(f"{where}: unexpected keys {sorted(extra)}")
        name = step.get("registry_name")
        if name not in ALLOWED_PROCESSOR_STEPS:
            raise UntrustedPretrainedError(f"{where}: processor {str(name)[:120]!r} is not allowed")
        cfg = step.get("config", {})
        if not isinstance(cfg, dict):
            raise UntrustedPretrainedError(f"{where}: 'config' must be an object")
        state = step.get("state_file")
        if state is not None and (not isinstance(state, str) or not _STATE_FILE_RE.match(state)):
            raise UntrustedPretrainedError(f"{where}: invalid state_file {str(state)[:120]!r}")


def _load_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise UntrustedPretrainedError(f"{path.name}: not a regular file")
    if path.stat().st_size > _MAX_JSON_BYTES:
        raise UntrustedPretrainedError(f"{path.name}: too large")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UntrustedPretrainedError(f"{path.name}: invalid JSON ({exc})") from exc


def validate_policy_config(path: Path, *, expected_type: str | None = None) -> str:
    doc = _load_json(path)
    if not isinstance(doc, dict):
        raise UntrustedPretrainedError("config.json: not a JSON object")
    ptype = doc.get("type")
    if ptype not in POLICY_TYPES:
        raise UntrustedPretrainedError(f"config.json: unsupported policy type {str(ptype)[:60]!r}")
    if expected_type is not None and ptype != expected_type:
        raise UntrustedPretrainedError(f"config.json: policy type {ptype!r}, run trains {expected_type!r}")
    return str(ptype)


def validate_pretrained_dir(
    path: Path, *, expected_type: str | None = None, require_processors: bool = True
) -> None:
    """Raise :class:`UntrustedPretrainedError` unless ``path`` is safe for LeRobot to load."""
    if not path.is_dir():
        raise UntrustedPretrainedError(f"{path}: not a directory")
    validate_policy_config(path / "config.json", expected_type=expected_type)
    for name in PROCESSOR_FILES:
        f = path / name
        if not f.exists():
            if require_processors:
                raise UntrustedPretrainedError(f"{name}: missing")
            continue
        validate_processor_config(_load_json(f), source=name)
    # Any other JSON that looks like a processor pipeline (custom config_filename) is checked too.
    for f in sorted(path.glob("*.json")):
        if f.name in PROCESSOR_FILES or f.name in ("config.json", "train_config.json"):
            continue
        doc = _load_json(f)
        if isinstance(doc, dict) and "steps" in doc:
            validate_processor_config(doc, source=f.name)
