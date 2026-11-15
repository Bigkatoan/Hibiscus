"""SEC-auth-04 residual (phase5-reverify N1/N8): the API access log redacts invite tokens in any
path form (duplicate slashes, percent-encoded separators, token= in a path)."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from app.core.middleware import redact_path
from tests.auth.fixtures import Ctx

TOK = "Tk_" + "a1B2" * 10


@pytest.mark.parametrize(
    "path",
    [
        f"/api/v1/auth/invites/{TOK}",
        f"/api/v1//auth/invites/{TOK}",
        f"/api/v1/auth//invites//{TOK}/accept",
        f"//api/v1/auth/invites/{TOK}",
        f"/api/v1/auth%2Finvites%2F{TOK}",
        f"/api/v1/AUTH/INVITES/{TOK}",
        f"/invite/{TOK}",
        f"/x/token={TOK}",
        f"/x/next%3Dtoken%3D{TOK}",
    ],
)
def test_redact_path_variants(path: str) -> None:
    out = redact_path(path)
    assert TOK not in out and "REDACTED" in out


def test_redact_path_keeps_named_routes() -> None:
    for p in ("/api/v1/auth/invites/preview", "/api/v1/auth/invites/accept", "/api/v1/runs"):
        assert redact_path(p) == p


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


async def test_double_slash_invite_path_is_redacted_in_access_log(ctx: Ctx) -> None:
    access = logging.getLogger("hibiscus.access")
    handler, level = _Records(), access.level
    access.addHandler(handler)
    access.setLevel(logging.INFO)
    try:
        anon: Any = ctx.client(validate=False)
        await anon.http.get(f"/api/v1//auth/invites/{TOK}")
        await anon.http.get(f"/api/v1/auth//invites/{TOK}")
    finally:
        access.removeHandler(handler)
        access.setLevel(level)
    paths = [str(getattr(r, "path", "")) for r in handler.records]
    assert len(paths) >= 2 and not any(TOK in p for p in paths), paths


# ---------------------------------------------------------------------------------------------
# N7: a dev key file planted by someone else is never trusted
# ---------------------------------------------------------------------------------------------
def _write_keys(path: Any, mode: int) -> None:
    import json as _json

    from app.core.settings import _random_keys

    path.write_text(_json.dumps(_random_keys()))
    path.chmod(mode)


def test_dev_keys_file_with_loose_mode_is_refused(tmp_path: Any) -> None:
    from app.core.settings import _dev_keys

    f = tmp_path / "k.json"
    _write_keys(f, 0o644)
    with pytest.raises(ValueError, match="not 0600"):
        _dev_keys("", str(f))
    f.chmod(0o600)
    assert _dev_keys("", str(f))["cursor_secret"]


def test_dev_keys_symlink_is_refused(tmp_path: Any) -> None:
    from app.core.settings import _dev_keys

    real = tmp_path / "real.json"
    _write_keys(real, 0o600)
    link = tmp_path / "k.json"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="symlink"):
        _dev_keys("", str(link))


def test_dev_keys_file_owned_by_another_uid_is_refused(tmp_path: Any, monkeypatch: Any) -> None:
    import os as _os

    from app.core import settings as settings_mod

    f = tmp_path / "k.json"
    _write_keys(f, 0o600)
    real = _os.geteuid()
    monkeypatch.setattr(_os, "geteuid", lambda: real + 1)
    with pytest.raises(ValueError, match="owned by uid"):
        settings_mod._dev_keys("", str(f))


def test_default_dev_keys_path_is_per_user(monkeypatch: Any, tmp_path: Any) -> None:
    import os as _os

    from app.core.settings import _default_dev_keys_path

    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    assert _default_dev_keys_path().endswith(f"hibiscus-dev-keys-{_os.geteuid()}.json")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert _default_dev_keys_path() == str(tmp_path / "hibiscus-dev-keys.json")
