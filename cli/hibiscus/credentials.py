"""PAT storage: OS keyring first, ``credentials.json`` (mode 0600) as fallback.

Resolution order for reading a token:
1. ``$HIBISCUS_TOKEN`` (CI / scripts; never persisted)
2. OS keyring (service ``hibiscus``, username = API base URL) unless ``$HIBISCUS_KEYRING=0``
3. ``<config_dir>/credentials.json`` ``{"<server>": "<token>"}`` (0600, refused if group/other readable)

Headless collect machines often have no usable keyring backend (``keyring.backends.fail``);
those are detected and the file fallback is used transparently.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from hibiscus.config import config_dir, read_json, write_private

SERVICE = "hibiscus"
PAT_RE = re.compile(r"^hbp_[A-Za-z0-9]{8}_[A-Za-z0-9_-]{43}$")


class CredentialError(Exception):
    pass


def looks_like_pat(token: str) -> bool:
    return bool(PAT_RE.match(token))


def token_prefix(token: str) -> str:
    """``hbp_ABCDEFGH_…`` -> ``ABCDEFGH`` (safe to display / log)."""
    parts = token.split("_")
    return parts[1] if len(parts) >= 3 else "?"


def _keyring_enabled() -> bool:
    return os.environ.get("HIBISCUS_KEYRING", "1").lower() not in ("0", "false", "no", "off")


def _usable_keyring() -> object | None:
    """Return the active keyring backend, or None if it is the ``fail``/null backend or broken."""
    if not _keyring_enabled():
        return None
    try:
        import keyring
        from keyring.backends import fail
    except Exception:  # pragma: no cover - keyring is a hard dependency
        return None
    try:
        backend = keyring.get_keyring()
    except Exception:
        return None
    if isinstance(backend, fail.Keyring):
        return None
    try:
        if float(backend.priority) <= 0:
            return None
    except Exception:
        return None
    return backend


def credentials_file() -> Path:
    return config_dir() / "credentials.json"


def _read_file_store() -> dict[str, str]:
    path = credentials_file()
    if not path.exists():
        return {}
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise CredentialError(
            f"{path} is readable by other users (mode {mode:o}); run `chmod 600 {path}` or `hibiscus logout`"
        )
    data = read_json(path) or {}
    return {str(k): str(v) for k, v in data.items()}


def _write_file_store(store: dict[str, str]) -> None:
    path = credentials_file()
    if not store:
        path.unlink(missing_ok=True)
        return
    write_private(path, json.dumps(store, indent=2) + "\n")


@dataclass(frozen=True)
class StoredToken:
    token: str
    source: str  # env | keyring | file


def save_token(server: str, token: str) -> str:
    """Persist the PAT; returns where it was stored (``keyring`` or the file path)."""
    backend = _usable_keyring()
    if backend is not None:
        try:
            import keyring

            keyring.set_password(SERVICE, server, token)
            # drop a stale file copy so there is exactly one persisted secret
            store = _read_file_store()
            if store.pop(server, None) is not None:
                _write_file_store(store)
            return "keyring"
        except Exception:  # noqa: S110 - any keyring failure falls back to the 0600 file
            pass
    store = _read_file_store()
    store[server] = token
    _write_file_store(store)
    return str(credentials_file())


def load_token(server: str) -> StoredToken | None:
    env = os.environ.get("HIBISCUS_TOKEN")
    if env:
        return StoredToken(env.strip(), "env")
    backend = _usable_keyring()
    if backend is not None:
        try:
            import keyring

            value = keyring.get_password(SERVICE, server)
        except Exception:
            value = None
        if value:
            return StoredToken(value, "keyring")
    value = _read_file_store().get(server)
    if value:
        return StoredToken(value, "file")
    return None


def delete_token(server: str) -> bool:
    removed = False
    backend = _usable_keyring()
    if backend is not None:
        try:
            import keyring

            keyring.delete_password(SERVICE, server)
            removed = True
        except Exception:  # noqa: S110 - absent entry / locked keyring: nothing to delete there
            pass
    store = _read_file_store()
    if store.pop(server, None) is not None:
        _write_file_store(store)
        removed = True
    return removed
