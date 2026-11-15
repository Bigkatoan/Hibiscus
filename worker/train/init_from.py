"""``init_from.hf_repo_id``: fetch only the weights + config of a Hub repo (SEC-input-1).

Never hand a Hub repo id to ``lerobot-train`` (it would download and import whatever
``policy_preprocessor.json`` the repo contains). Instead:

1. list the repo files and refuse it when the allowed files are missing or bigger than the cap;
2. ``snapshot_download(allow_patterns=HF_ALLOW_PATTERNS)`` into the run's scratch dir, so
   processor JSONs, state files, code and anything else never reach the disk;
3. drop anything else that is there anyway, check ``config.json`` (known policy type, the run's
   type) and generate processor JSONs locally (``train/trusted_processors.py``, fresh interpreter,
   allow-listed env);
4. run :func:`core.pretrained_guard.validate_pretrained_dir` on the result.

The caller passes the LOCAL directory as ``--policy.pretrained_path``.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from core.pretrained_guard import UntrustedPretrainedError, validate_policy_config, validate_pretrained_dir

log = logging.getLogger(__name__)

HF_ALLOW_PATTERNS = ["config.json", "model.safetensors", "train_config.json"]
REQUIRED_FILES = ("config.json", "model.safetensors")
_GENERATOR = Path(__file__).resolve().parent / "trusted_processors.py"


class InitFromError(RuntimeError):
    """``code`` is a run error code: ``config_invalid`` (user) or ``checkpoint_corrupt`` (infra)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _repo_sizes(repo_id: str, token: str | None) -> dict[str, int]:
    from huggingface_hub import HfApi

    info = HfApi().model_info(repo_id, files_metadata=True, token=token)
    return {s.rfilename: int(s.size or 0) for s in (info.siblings or [])}


def _download(repo_id: str, dest: Path, cache_dir: Path, token: str | None) -> None:
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id,
        repo_type="model",
        allow_patterns=list(HF_ALLOW_PATTERNS),
        local_dir=str(dest),
        cache_dir=str(cache_dir),
        token=token,
    )


def generate_processors(
    policy_dir: Path,
    *,
    dataset_root: Path,
    repo_id: str,
    env: Mapping[str, str],
    python: str | None = None,
    timeout_s: float = 600.0,
) -> None:
    argv = [
        python or sys.executable,
        "-I",
        str(_GENERATOR),
        "--policy-dir",
        str(policy_dir),
        "--dataset-root",
        str(dataset_root),
        "--repo-id",
        repo_id,
    ]
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv, capture_output=True, text=True, timeout=timeout_s, env=dict(env), check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise InitFromError("checkpoint_corrupt", "processor generation timed out") from exc
    line = next((ln for ln in reversed(proc.stdout.strip().splitlines()) if ln.startswith("{")), None)
    data: dict[str, Any] = json.loads(line) if line else {}
    if proc.returncode != 0 or not data.get("ok"):
        detail = data.get("error") or (proc.stderr or proc.stdout)[-1500:]
        raise InitFromError("config_invalid", f"init_from: cannot build processors: {detail}")


def fetch_hf_init(
    repo_id: str,
    dest: Path,
    *,
    policy_type: str,
    dataset_root: Path,
    dataset_repo_id: str,
    cache_dir: Path,
    env: Mapping[str, str],
    max_bytes: int,
    token: str | None = None,
    list_sizes: Callable[[str, str | None], dict[str, int]] = _repo_sizes,
    download: Callable[[str, Path, Path, str | None], None] = _download,
) -> Path:
    """Return a local, validated ``pretrained_model`` dir built from ``repo_id``."""
    try:
        sizes = list_sizes(repo_id, token)
    except Exception as exc:
        raise InitFromError("checkpoint_corrupt", f"init_from {repo_id}: hub lookup failed: {exc}") from exc
    missing = [f for f in REQUIRED_FILES if f not in sizes]
    if missing:
        raise InitFromError("config_invalid", f"init_from {repo_id}: repo has no {', '.join(missing)}")
    total = sum(sizes.get(f, 0) for f in HF_ALLOW_PATTERNS)
    if total > max_bytes:
        raise InitFromError(
            "config_invalid", f"init_from {repo_id}: {total} bytes is above the {max_bytes} byte limit"
        )
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    try:
        download(repo_id, dest, cache_dir, token)
    except Exception as exc:
        raise InitFromError("checkpoint_corrupt", f"init_from {repo_id}: download failed: {exc}") from exc
    # Defense in depth: keep only the allowed files, whatever the downloader left there.
    for p in list(dest.iterdir()):
        if p.name in HF_ALLOW_PATTERNS and p.is_file() and not p.is_symlink():
            continue
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
        else:
            p.unlink()
    got = sum(p.stat().st_size for p in dest.iterdir())
    if got > max_bytes:
        raise InitFromError("config_invalid", f"init_from {repo_id}: downloaded files exceed the limit")
    for f in REQUIRED_FILES:
        if not (dest / f).is_file():
            raise InitFromError("checkpoint_corrupt", f"init_from {repo_id}: {f} missing after download")
    try:
        validate_policy_config(dest / "config.json", expected_type=policy_type)
    except UntrustedPretrainedError as exc:
        raise InitFromError("config_invalid", f"init_from {repo_id}: {exc}") from exc
    generate_processors(dest, dataset_root=dataset_root, repo_id=dataset_repo_id, env=env)
    try:
        validate_pretrained_dir(dest, expected_type=policy_type)
    except UntrustedPretrainedError as exc:  # pragma: no cover - our own generator output
        raise InitFromError("config_invalid", f"init_from {repo_id}: {exc}") from exc
    log.info("init_from %s fetched (%d bytes) into %s", repo_id, got, dest)
    return dest
