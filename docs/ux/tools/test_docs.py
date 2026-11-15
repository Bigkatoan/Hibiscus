"""Docs checks: relative Markdown links in docs/ux and docs/user-guide resolve, vi/en user guides
stay paired, and docs/ux/error-catalogue.md matches the i18n JSON.

The i18n resources themselves are tested by vitest (frontend/src/lib/i18n.test.ts).

    env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run --no-project --python 3.12 \
        --with pytest --with pyyaml pytest -q docs/ux/tools
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
DOC_DIRS = [REPO / "docs" / "ux", REPO / "docs" / "user-guide"]
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _md_files() -> list[Path]:
    return sorted(p for d in DOC_DIRS for p in d.rglob("*.md"))


@pytest.mark.parametrize("path", _md_files(), ids=lambda p: str(p.relative_to(REPO)))
def test_relative_links_resolve(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    broken = []
    for target in LINK_RE.findall(text):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        file_part = target.split("#", 1)[0]
        if not (path.parent / file_part).resolve().exists():
            broken.append(target)
    assert not broken, broken


def test_user_guide_has_same_chapters_in_vi_and_en() -> None:
    guide = REPO / "docs" / "user-guide"
    vi = sorted(p.name[:2] for p in (guide / "vi").glob("*.md"))
    en = sorted(p.name[:2] for p in (guide / "en").glob("*.md"))
    assert vi == en and len(vi) >= 8


def test_user_guide_never_promises_lelab_inference() -> None:
    """ADR-0011: LeLab has no inference; the guide must say so and point to LeRobot CLI in the venv."""
    vi = (REPO / "docs" / "user-guide" / "vi" / "06-chay-tren-robot.md").read_text(encoding="utf-8")
    en = (REPO / "docs" / "user-guide" / "en" / "06-run-on-robot.md").read_text(encoding="utf-8")
    assert "LeLab hiện chưa có chức năng chạy policy" in vi
    assert "LeLab cannot run policies yet" in en
    for text in (vi, en):
        assert "~/lelab/leLab/.venv" in text and "lerobot-rollout" in text


def test_error_catalogue_markdown_is_up_to_date() -> None:
    spec = importlib.util.spec_from_file_location(
        "gen_error_catalogue", REPO / "docs" / "ux" / "tools" / "gen_error_catalogue.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    current = (REPO / "docs" / "ux" / "error-catalogue.md").read_text(encoding="utf-8")
    assert mod.render(REPO) == current, (
        "stale: uv run --no-project --with pyyaml python docs/ux/tools/gen_error_catalogue.py"
    )
