from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from validate.tests.synth import SynthSpec, make_v30

GOLDEN_RAR = Path(
    os.environ.get("HIBISCUS_GOLDEN_RAR", "~/lelab/Picknplace_20261114_221710.rar")
)
GOLDEN_DIR = Path(
    os.environ.get("HIBISCUS_GOLDEN_DIR", "~/datasets/robotics/so101_picknplace_20261114")
)


@pytest.fixture(scope="session")
def synth_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("synth_template")
    make_v30(base / "my_dataset", SynthSpec())
    return base / "my_dataset"


@pytest.fixture
def synth_ds(tmp_path: Path, synth_template: Path) -> Path:
    """A fresh copy of a valid 3-episode v3.0 dataset at ``<tmp>/src/my_dataset``."""
    dst = tmp_path / "src" / "my_dataset"
    shutil.copytree(synth_template, dst)
    return dst


@pytest.fixture(scope="session")
def golden_rar() -> Path:
    if not GOLDEN_RAR.is_file():
        pytest.fail(f"golden archive missing: {GOLDEN_RAR} (set HIBISCUS_GOLDEN_RAR)")
    return GOLDEN_RAR
