"""``push_model_hub`` CPU job (QC-backend-02; ``POST /models/{id}/push-hub``).

Payload = OpenAPI ``HubPushRequest`` ``{repo_id, private, include_onnx}``. Pushes the delivered
bundle (``models.bundle_uri``) with the token the user stored (``user_secrets`` kind ``hf_token``,
AES-256-GCM with ``HIBISCUS_DATA_KEY``):

* repo root = ``pretrained_model/`` (what ``--policy.path=<org>/<name>`` loads in LeRobot) plus
  ``README.md`` = MODEL_CARD.md with Hub front matter, and ``MANIFEST.json``;
* ``onnx/`` only when ``include_onnx`` is true.

The pushed repo is created when missing (``private`` as requested). Errors from the Hub are user
errors (bad token, no write access) and fail the job with ``hub_push_failed``.
"""

from __future__ import annotations

import logging
import re
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("hibiscus.validate.hub")
HF_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")


class HubPushError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PushRequest:
    repo_id: str
    private: bool = True
    include_onnx: bool = False

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> PushRequest:
        repo = str(payload.get("repo_id") or "")
        if not HF_REPO_RE.match(repo) or ".." in repo:
            raise HubPushError("hub_repo_invalid", f"invalid Hub repository id {repo!r}")
        return cls(repo, bool(payload.get("private", True)), bool(payload.get("include_onnx", False)))


def extract_bundle(zip_path: Path, dest: Path) -> Path:
    """Unzip the bundle (members checked: one top dir, no absolute / ``..`` paths)."""
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if not names:
            raise HubPushError("bundle_invalid", "empty bundle")
        top = names[0].split("/", 1)[0]
        for n in names:
            parts = n.split("/")
            if n.startswith("/") or "\\" in n or ".." in parts or parts[0] != top:
                raise HubPushError("bundle_invalid", f"unexpected member {n!r}")
        zf.extractall(dest)
    return dest / top


def stage_repo(
    bundle_dir: Path, out: Path, *, include_onnx: bool, policy_type: str, dataset: str | None
) -> Path:
    from export.model_card import hub_readme

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(bundle_dir / "pretrained_model", out)
    card = (bundle_dir / "MODEL_CARD.md").read_text() if (bundle_dir / "MODEL_CARD.md").is_file() else ""
    (out / "README.md").write_text(hub_readme(card, policy_type=policy_type, dataset_repo_id=dataset))
    if (bundle_dir / "MANIFEST.json").is_file():
        shutil.copyfile(bundle_dir / "MANIFEST.json", out / "MANIFEST.json")
    if include_onnx and (bundle_dir / "onnx").is_dir():
        shutil.copytree(bundle_dir / "onnx", out / "onnx")
    return out


def _default_api(token: str) -> Any:
    from huggingface_hub import HfApi

    return HfApi(token=token)


def push(
    folder: Path,
    req: PushRequest,
    *,
    token: str,
    commit_message: str,
    api_factory: Callable[[str], Any] = _default_api,
) -> str:
    """Create the repo if needed and upload ``folder``; returns the commit URL / id."""
    api = api_factory(token)
    try:
        api.create_repo(req.repo_id, repo_type="model", private=req.private, exist_ok=True)
        info = api.upload_folder(
            folder_path=str(folder), repo_id=req.repo_id, repo_type="model", commit_message=commit_message
        )
    except Exception as exc:
        raise HubPushError("hub_push_failed", f"{type(exc).__name__}: {exc}"[:2000]) from exc
    return str(getattr(info, "commit_url", None) or info)
