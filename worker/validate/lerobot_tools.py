"""Thin wrappers around LeRobot 0.7.1's own tools, run as subprocesses (argv lists, Hub offline).

* v2.1 -> v3.0: ``lerobot/scripts/convert_dataset_v21_to_v30.py`` (``convert_dataset``), in place.
* merge: ``lerobot.datasets.aggregate.aggregate_datasets`` (what ``lerobot-edit-dataset`` merge uses).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

CONVERTIBLE_VERSIONS = {"v2.1"}
SUPPORTED_VERSION = "v3.0"


def lerobot_version() -> str:
    try:
        return metadata.version("lerobot")
    except metadata.PackageNotFoundError:
        return "unknown"


@dataclass(slots=True)
class ToolResult:
    ok: bool
    message: str


def _env(tmp_home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "HOME", "PYTHONPATH")}
    env.update(
        {
            "HF_HUB_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "HF_LEROBOT_HOME": str(tmp_home),
            "HF_HOME": str(tmp_home / "hf"),
            "TQDM_DISABLE": "1",
        }
    )
    return env


def convert_v21_to_v30(root: Path, timeout_s: float = 6 * 3600) -> ToolResult:
    """Convert the dataset at ``root`` in place. LeRobot leaves ``<root>_old``; it is removed."""
    tmp_home = root.parent / ".lerobot_home"
    tmp_home.mkdir(exist_ok=True)
    argv = [
        sys.executable,
        "-m",
        "lerobot.scripts.convert_dataset_v21_to_v30",
        "--repo-id",
        f"local/{root.name}",
        "--root",
        str(root),
        "--push-to-hub",
        "false",
    ]
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv
            argv,
            capture_output=True,
            env=_env(tmp_home),
            timeout=timeout_s,
            check=False,
            cwd=str(root.parent),
        )
    except subprocess.TimeoutExpired:
        return ToolResult(False, "conversion timed out")
    finally:
        shutil.rmtree(tmp_home, ignore_errors=True)
    old = root.parent / f"{root.name}_old"
    if old.exists():
        shutil.rmtree(old, ignore_errors=True)
    stale = root.parent / f"{root.name}_v30"
    if stale.exists():
        shutil.rmtree(stale, ignore_errors=True)
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace").strip().splitlines()[-3:]
        return ToolResult(False, " | ".join(tail)[-500:] or f"exit {proc.returncode}")
    return ToolResult(True, "converted")


_MERGE_SNIPPET = """
import json, sys
from pathlib import Path
from lerobot.datasets.aggregate import aggregate_datasets
args = json.loads(sys.stdin.read())
aggregate_datasets(
    repo_ids=args["repo_ids"], aggr_repo_id=args["out_repo_id"],
    roots=[Path(r) for r in args["roots"]], aggr_root=Path(args["out_root"]),
)
"""


def merge_datasets(roots: list[Path], out_root: Path, timeout_s: float = 6 * 3600) -> ToolResult:
    out_root.parent.mkdir(parents=True, exist_ok=True)
    tmp_home = out_root.parent / ".lerobot_home_merge"
    tmp_home.mkdir(exist_ok=True)
    payload = {
        "repo_ids": [f"local/src{i}" for i in range(len(roots))],
        "roots": [str(r) for r in roots],
        "out_repo_id": "local/merged",
        "out_root": str(out_root),
    }
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, code is a constant
            [sys.executable, "-c", _MERGE_SNIPPET],
            input=json.dumps(payload).encode(),
            capture_output=True,
            env=_env(tmp_home),
            timeout=timeout_s,
            check=False,
            cwd=str(out_root.parent),
        )
    except subprocess.TimeoutExpired:
        return ToolResult(False, "merge timed out")
    finally:
        shutil.rmtree(tmp_home, ignore_errors=True)
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace").strip().splitlines()[-3:]
        return ToolResult(False, " | ".join(tail)[-500:] or f"exit {proc.returncode}")
    return ToolResult(True, "merged")
