"""Run-domain settings (env ``HIBISCUS_*``) that are not part of ``app.core.settings``.

Infrastructure (database, Redis, S3, cursor secret) comes from the core :class:`~app.core.settings.Settings`
only; this class holds the knobs specific to runs/models.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.storage import BUCKET_ARTIFACTS

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Policy fields that name a Hugging Face model repo loaded by ``transformers`` in the child.
HUB_MODEL_FIELDS: tuple[str, ...] = ("vlm_model_name", "text_tokenizer_name")
DEFAULT_VLM_MODELS: tuple[str, ...] = (
    "huggingfacetb/smolvlm2-500m-video-instruct",  # smolvla default
    "google/paligemma-3b-pt-224",  # pi0 / pi05 tokenizer default
)
_HUB_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")


class RunsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HIBISCUS_", extra="ignore")

    bucket_artifacts: str = BUCKET_ARTIFACTS
    #: Directory holding ``api/policy-schemas`` (copied into the API image by A8).
    policy_schemas_dir: Path = REPO_ROOT / "api" / "policy-schemas"
    sse_heartbeat_s: float = 15.0
    sse_poll_s: float = 2.0
    reaper_interval_s: float = 15.0
    gpu_offline_after_s: float = 30.0
    run_reaper: bool = True
    #: SEC-input-1: Hugging Face repos a run may start from via ``init_from.hf_repo_id``. LeRobot
    #: imports the processor classes named by a repo's ``policy_*processor.json`` while loading it,
    #: so a user-controlled repo is code execution on the GPU worker. Platform-admin managed
    #: (``HIBISCUS_INIT_FROM_HF_ALLOWLIST``: comma-separated or JSON list of ``org/name``, matched
    #: case-insensitively). Empty (the default) refuses every ``hf_repo_id``.
    init_from_hf_allowlist: Annotated[frozenset[str], NoDecode] = frozenset()
    #: Phase-5 re-verify N5: Hub repos a policy may name as its VLM backbone / tokenizer
    #: (smolvla ``vlm_model_name``, pi0/pi05 ``text_tokenizer_name``). The child runs online for
    #: these policies and hands the value to ``transformers.*.from_pretrained``, so free-form values
    #: (any Hub repo, or a local path on the GPU worker) are refused. Same format as
    #: ``HIBISCUS_INIT_FROM_HF_ALLOWLIST`` (``HIBISCUS_VLM_MODEL_ALLOWLIST``); the default is the
    #: official bases LeRobot 0.7.1 uses.
    vlm_model_allowlist: Annotated[frozenset[str], NoDecode] = frozenset(DEFAULT_VLM_MODELS)
    #: QC-backend-02: ``push_model_hub`` jobs are only accepted when a worker handles them
    #: (``HIBISCUS_HUB_PUSH_ENABLED``). Off => ``POST /models/{id}/push-hub`` answers 501.
    hub_push_enabled: bool = False

    @field_validator("init_from_hf_allowlist", "vlm_model_allowlist", mode="before")
    @classmethod
    def _split_allowlist(cls, v: object) -> object:
        if isinstance(v, str):
            raw = v.strip()
            if raw.startswith("["):
                import json

                v = json.loads(raw)
            else:
                v = [x for x in (p.strip() for p in raw.split(",")) if x]
        if isinstance(v, (list, tuple, set, frozenset)):
            return frozenset(str(x).strip().lower() for x in v if str(x).strip())
        return v

    def hf_repo_allowed(self, repo_id: str) -> bool:
        return repo_id.strip().lower() in self.init_from_hf_allowlist

    def hub_model_allowed(self, name: str) -> bool:
        return hub_model_allowed(name, self.vlm_model_allowlist)


def hub_model_allowed(name: object, allowlist: frozenset[str]) -> bool:
    """A plain ``org/name`` Hub id on the allow-list; never a local path, URL or ``..``."""
    if not isinstance(name, str) or not _HUB_REPO_RE.fullmatch(name) or ".." in name:
        return False
    return name.lower() in allowlist


def disallowed_hub_models(policy: dict[str, object], allowlist: frozenset[str]) -> dict[str, object]:
    """The ``HUB_MODEL_FIELDS`` of a resolved policy config whose value is not allowed."""
    return {
        f: policy[f] for f in HUB_MODEL_FIELDS if f in policy and not hub_model_allowed(policy[f], allowlist)
    }


@lru_cache(maxsize=1)
def get_runs_settings() -> RunsSettings:
    return RunsSettings()
