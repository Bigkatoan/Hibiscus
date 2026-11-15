"""Local configuration: server URL, workspace, on-disk locations.

Locations (platformdirs, overridable for tests / multiple installs):

* config  ``$HIBISCUS_CONFIG_DIR`` or ``~/.config/hibiscus`` -> ``config.json``,
  ``credentials.json`` (token fallback)
* state   ``$HIBISCUS_STATE_DIR``  or ``~/.local/state/hibiscus`` -> upload resume files, watch ledger
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import platformdirs

DEFAULT_SERVER = "https://robot.example.com/api/v1"
API_PREFIX = "/api/v1"


def config_dir() -> Path:
    env = os.environ.get("HIBISCUS_CONFIG_DIR")
    return Path(env) if env else Path(platformdirs.user_config_dir("hibiscus", appauthor=False))


def state_dir() -> Path:
    env = os.environ.get("HIBISCUS_STATE_DIR")
    return Path(env) if env else Path(platformdirs.user_state_dir("hibiscus", appauthor=False))


def normalize_server(url: str) -> str:
    """Return the API base URL (``.../api/v1``) for a user-supplied server URL.

    ``https://robot.example.com`` and ``https://robot.example.com/api/v1/`` both map to
    ``https://robot.example.com/api/v1``. Only http(s) URLs are accepted.
    """
    raw = url.strip()
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(f"invalid server URL: {url!r}")
    path = parts.path.rstrip("/")
    if not path.endswith(API_PREFIX):
        path = path + API_PREFIX
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def write_private(path: Path, data: str) -> None:
    """Atomically write ``data`` to ``path`` with mode 0600 (parent dirs 0700)."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


@dataclass
class Config:
    server: str = DEFAULT_SERVER
    workspace_id: str | None = None
    workspace_name: str | None = None
    user_display_name: str | None = None
    token_prefix: str | None = None

    @classmethod
    def path(cls) -> Path:
        return config_dir() / "config.json"

    @classmethod
    def load(cls) -> Config:
        data = read_json(cls.path()) or {}
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        cfg = cls(**known)
        env_server = os.environ.get("HIBISCUS_SERVER")
        if env_server:
            cfg.server = normalize_server(env_server)
        env_ws = os.environ.get("HIBISCUS_WORKSPACE_ID")
        if env_ws:
            cfg.workspace_id = env_ws
        return cfg

    def save(self) -> None:
        write_private(self.path(), json.dumps(asdict(self), indent=2) + "\n")
