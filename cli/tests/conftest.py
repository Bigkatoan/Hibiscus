from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import respx

from hibiscus.api import Backoff, HibiscusApi
from tests.fake_server import BASE, TOKEN, FakeHibiscus

GOLDEN_DATASET = Path.home() / "datasets/robotics/so101_picknplace_20261114"
GOLDEN_RAR = Path.home() / "lelab/Picknplace_20261114_221710.rar"
ACT_CHECKPOINT = Path.home() / "lelab/outputs/train/act_picknplace/checkpoints/010000/pretrained_model"


def pytest_configure(config: pytest.Config) -> None:
    """Human-readable output is asserted as plain text. CI exports FORCE_COLOR=1, which rich honours
    when ``hibiscus.main`` builds its module-level consoles (at test-module import, i.e. after this
    hook), so drop it here; ``--json`` output is plain regardless (test_json_output_is_plain)."""
    for var in ("FORCE_COLOR", "TTY_COMPATIBLE", "TTY_INTERACTIVE"):
        os.environ.pop(var, None)


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test gets its own config/state dirs and no ambient credentials."""
    home = tmp_path / "home"
    monkeypatch.setenv("HIBISCUS_CONFIG_DIR", str(home / "config"))
    monkeypatch.setenv("HIBISCUS_STATE_DIR", str(home / "state"))
    monkeypatch.setenv("HIBISCUS_KEYRING", "0")
    for var in ("HIBISCUS_TOKEN", "HIBISCUS_SERVER", "HIBISCUS_WORKSPACE_ID"):
        monkeypatch.delenv(var, raising=False)
    return home


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def fake(tmp_path: Path) -> Iterator[FakeHibiscus]:
    server = FakeHibiscus(tmp_path / "server")
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        server.mount(router)
        yield server


@pytest.fixture
def api(fake: FakeHibiscus, sleeps: list[float]) -> Iterator[HibiscusApi]:
    backoff = Backoff(attempts=6, sleep=sleeps.append, jitter=False)
    client = HibiscusApi(BASE, TOKEN, workspace_id=fake.workspace_id, backoff=backoff)
    yield client
    client.close()
