from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from export.tests.checkpoints import ACT_CHECKPOINT, GOLDEN_DATASET, make_random_checkpoint

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = REPO_ROOT / "api" / "bundle-schemas"

os.environ.setdefault("HF_HUB_OFFLINE", "1")

requires_golden = pytest.mark.skipif(
    not (GOLDEN_DATASET / "meta" / "info.json").is_file(), reason="golden dataset not available"
)
requires_act = pytest.mark.skipif(
    not (ACT_CHECKPOINT / "config.json").is_file(), reason="real ACT checkpoint not available"
)


def load_schema(name: str) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((SCHEMAS / name).read_text())
    return doc


def validate(doc: Any, schema_name: str) -> None:
    import jsonschema

    schema = load_schema(schema_name)
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(doc)


def openapi_schema(name: str) -> dict[str, Any]:
    import yaml

    spec = yaml.safe_load((REPO_ROOT / "api" / "openapi.yaml").read_text())
    schema: dict[str, Any] = spec["components"]["schemas"][name]
    return schema


@pytest.fixture(scope="session")
def ckpt_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # every small_* checkpoint takes its features and normalizer stats from the golden dataset,
    # which only exists on the lab machine (HIBISCUS_GOLDEN_DATASET); CI runners skip these tests.
    if not (GOLDEN_DATASET / "meta" / "info.json").is_file():
        pytest.skip(f"golden dataset not available: {GOLDEN_DATASET} (set HIBISCUS_GOLDEN_DATASET)")
    return tmp_path_factory.mktemp("ckpts")


@pytest.fixture(scope="session")
def small_act(ckpt_root: Path) -> Path:
    return make_random_checkpoint("act", ckpt_root / "act" / "pretrained_model")


@pytest.fixture(scope="session")
def small_diffusion(ckpt_root: Path) -> Path:
    return make_random_checkpoint("diffusion", ckpt_root / "diffusion" / "pretrained_model")


@pytest.fixture(scope="session")
def small_diffusion_ddim(ckpt_root: Path) -> Path:
    return make_random_checkpoint(
        "diffusion",
        ckpt_root / "diffusion_ddim" / "pretrained_model",
        noise_scheduler_type="DDIM",
        beta_schedule="linear",
        prediction_type="sample",
        num_inference_steps=5,
        clip_sample=False,
    )


@pytest.fixture(scope="session")
def small_vqbet(ckpt_root: Path) -> Path:
    return make_random_checkpoint("vqbet", ckpt_root / "vqbet" / "pretrained_model")
