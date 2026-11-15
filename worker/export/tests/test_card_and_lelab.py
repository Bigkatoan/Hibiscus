"""QC-ml-1 (LeLab compatibility facts) and QC-ml-3 (MODEL_CARD split row)."""

from __future__ import annotations

import re
from importlib import metadata
from pathlib import Path

import pytest

from export.lelab_compat import (
    EXTRA_REQUIREMENTS,
    LELAB_MISSING_MODULES,
    extra_requirements,
    pip_command,
    required_modules,
)
from export.load_check import run_load_checks
from export.model_card import episode_ranges, split_row
from export.run_on_robot import render_run_on_robot
from export.tests.checkpoints import GOLDEN_DATASET, GOLDEN_REPO_ID, LELAB_PYTHON
from export.tests.conftest import requires_golden


def test_split_row_counts_and_ranges() -> None:
    assert episode_ranges([0, 1, 2, 5, 7, 8]) == "0-2, 5, 7-8"
    row = split_row(list(range(18)), [18, 19])
    assert row == "train: 18 episodes (0-17), held-out: 2 episodes (18-19)"
    assert split_row([0], []) == "train: 1 episode (0), held-out: none"


def _lerobot_extra_reqs() -> dict[str, set[str]]:
    """``extra -> {pip requirement}`` from lerobot 0.7.1's own metadata (``*-dep`` resolved)."""
    raw = metadata.requires("lerobot") or []
    by_extra: dict[str, list[str]] = {}
    for line in raw:
        req, _, marker = line.partition(";")
        m = re.search(r'extra == "([^"]+)"', marker)
        if m:
            by_extra.setdefault(m.group(1), []).append(req.strip())

    def resolve(extra: str) -> set[str]:
        out: set[str] = set()
        for r in by_extra.get(extra, []):
            sub = re.match(r"lerobot\[([^\]]+)\]", r)
            if sub:
                out |= resolve(sub.group(1))
            else:
                out.add(r.replace(" ", ""))
        return out

    return {e: resolve(e) for e in EXTRA_REQUIREMENTS}


def test_extra_requirements_match_lerobot_metadata() -> None:
    meta = _lerobot_extra_reqs()

    def norm(r: str) -> tuple[str, frozenset[str]]:
        name = re.split(r"[<>=!~]", r, maxsplit=1)[0].lower()
        return name, frozenset(re.findall(r"[<>=!~]=?[^,]+", r))

    for extra, reqs in EXTRA_REQUIREMENTS.items():
        have = {norm(r) for r in meta[extra]}
        for r in reqs:
            assert norm(r) in have, (extra, r, sorted(meta[extra]))


def test_requirements_per_policy() -> None:
    assert extra_requirements("act") == [] and extra_requirements("vqbet") == []
    assert extra_requirements("diffusion") == ["diffusers>=0.38.0,<0.40.0"]
    assert "transformers>=5.22.0,<5.23.0" in extra_requirements("smolvla")
    assert "peft>=0.18.0,<1.0.0" in extra_requirements("act", peft=True)
    assert required_modules(extra_requirements("pi0")) == ["transformers", "scipy", "sentencepiece"]
    assert pip_command(["diffusers>=0.38.0,<0.40.0"]) == "pip install 'diffusers>=0.38.0,<0.40.0'"


def test_run_on_robot_precheck(tmp_path: Path) -> None:
    import subprocess

    script = render_run_on_robot(
        bundle_name="x_diffusion-r1-step10",
        robot_type="so101_follower",
        fps=30,
        cameras=[],
        task="pick",
        requirements=["diffusers>=0.38.0,<0.40.0"],
    )
    assert "import diffusers;" in script
    p = tmp_path / "run.sh"
    p.write_text(script)
    assert subprocess.run(["bash", "-n", str(p)], check=False).returncode == 0  # noqa: S603, S607


@requires_golden
@pytest.mark.parametrize("ptype", ["act", "diffusion"])
def test_emulated_lelab_check_agrees_with_real_lelab_venv(ptype: str, request: pytest.FixtureRequest) -> None:
    """The worker image has no LeLab venv: hiding LELAB_MISSING_MODULES must give the same
    verdict as the real ~/lelab/leLab/.venv (lerobot 0.7.1, no extras) on this box."""
    ckpt = request.getfixturevalue(f"small_{ptype}")
    load, lelab = run_load_checks(ckpt, dataset_root=GOLDEN_DATASET, repo_id=GOLDEN_REPO_ID, episode=19)
    assert load.ok
    assert lelab.ok is (ptype == "act")
    assert lelab.raw.get("blocked_modules") == sorted(LELAB_MISSING_MODULES)
    if LELAB_PYTHON.is_file():
        _, real = run_load_checks(
            ckpt,
            dataset_root=GOLDEN_DATASET,
            repo_id=GOLDEN_REPO_ID,
            episode=19,
            lelab_python=str(LELAB_PYTHON),
        )
        assert real.ok is lelab.ok, (real.detail, lelab.detail)
