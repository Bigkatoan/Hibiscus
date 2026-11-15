from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend

from hibiscus import credentials
from hibiscus.config import Config, normalize_server
from hibiscus.credentials import (
    CredentialError,
    delete_token,
    load_token,
    looks_like_pat,
    save_token,
    token_prefix,
)
from hibiscus.overrides import OverrideError, build_config, parse_value
from tests.fake_server import TOKEN

SERVER = "https://hibiscus.test/api/v1"


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        super().__init__()  # type: ignore[no-untyped-call]  # keyring base lacks annotations
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self.store:
            raise keyring.errors.PasswordDeleteError("missing")
        del self.store[(service, username)]


@pytest.fixture
def mem_keyring(monkeypatch: pytest.MonkeyPatch) -> Iterator[MemoryKeyring]:
    previous = keyring.get_keyring()
    kr = MemoryKeyring()
    keyring.set_keyring(kr)
    monkeypatch.setenv("HIBISCUS_KEYRING", "1")
    yield kr
    keyring.set_keyring(previous)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://robot.example.com", "https://robot.example.com/api/v1"),
        ("https://robot.example.com/", "https://robot.example.com/api/v1"),
        ("https://robot.example.com/api/v1/", "https://robot.example.com/api/v1"),
        ("robot.example.com", "https://robot.example.com/api/v1"),
        ("http://127.0.0.1:18100", "http://127.0.0.1:18100/api/v1"),
        ("https://h.example/prefix", "https://h.example/prefix/api/v1"),
    ],
)
def test_normalize_server(raw: str, expected: str) -> None:
    assert normalize_server(raw) == expected


def test_normalize_server_rejects_other_schemes() -> None:
    with pytest.raises(ValueError):
        normalize_server("ftp://x")


def test_config_roundtrip_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = Config.load()
    assert cfg.server == "https://robot.example.com/api/v1" and cfg.workspace_id is None
    cfg.workspace_id = "w1"
    cfg.save()
    assert Config.path().stat().st_mode & 0o777 == 0o600
    assert Config.load().workspace_id == "w1"
    monkeypatch.setenv("HIBISCUS_SERVER", "http://127.0.0.1:18100")
    monkeypatch.setenv("HIBISCUS_WORKSPACE_ID", "w2")
    cfg2 = Config.load()
    assert cfg2.server == "http://127.0.0.1:18100/api/v1" and cfg2.workspace_id == "w2"


def test_pat_helpers() -> None:
    assert looks_like_pat(TOKEN)
    assert not looks_like_pat("hbp_short_x")
    assert token_prefix(TOKEN) == "AbCd1234"


def test_file_fallback_is_0600(monkeypatch: pytest.MonkeyPatch) -> None:
    where = save_token(SERVER, TOKEN)
    path = credentials.credentials_file()
    assert where == str(path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    st = load_token(SERVER)
    assert st is not None and st.token == TOKEN and st.source == "file"
    assert load_token("https://other/api/v1") is None
    assert delete_token(SERVER)
    assert not path.exists() and load_token(SERVER) is None


def test_file_fallback_refuses_world_readable() -> None:
    save_token(SERVER, TOKEN)
    path = credentials.credentials_file()
    os.chmod(path, 0o644)
    with pytest.raises(CredentialError, match="readable by other users"):
        load_token(SERVER)


def test_env_token_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    save_token(SERVER, TOKEN)
    monkeypatch.setenv("HIBISCUS_TOKEN", "hbp_ENVENVEN_" + "e" * 43)
    st = load_token(SERVER)
    assert st is not None and st.source == "env" and st.token.startswith("hbp_ENVENVEN")


def test_keyring_preferred_and_moves_file_copy(mem_keyring: MemoryKeyring) -> None:
    # a stale file copy from an earlier keyring-less login
    monkey_file = credentials.credentials_file()
    monkey_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    monkey_file.write_text(json.dumps({SERVER: "old"}))
    os.chmod(monkey_file, 0o600)
    assert save_token(SERVER, TOKEN) == "keyring"
    assert mem_keyring.store[("hibiscus", SERVER)] == TOKEN
    assert not monkey_file.exists()
    st = load_token(SERVER)
    assert st is not None and st.source == "keyring"
    assert delete_token(SERVER)
    assert load_token(SERVER) is None


def test_fail_keyring_backend_falls_back_to_file(monkeypatch: pytest.MonkeyPatch) -> None:
    from keyring.backends import fail

    previous = keyring.get_keyring()
    keyring.set_keyring(fail.Keyring())  # type: ignore[no-untyped-call]  # untyped upstream
    monkeypatch.setenv("HIBISCUS_KEYRING", "1")
    try:
        assert save_token(SERVER, TOKEN) == str(credentials.credentials_file())
        st = load_token(SERVER)
        assert st is not None and st.source == "file"
    finally:
        keyring.set_keyring(previous)


def test_overrides() -> None:
    cfg = build_config(
        [
            "train.steps=300",
            "policy.chunk_size=50",
            "batch_size=4",
            "vision_backbone=resnet34",
            "train.peft.r=8",
            "policy.use_vae=false",
            "train.seed=null",
            'policy.normalization_mapping={"STATE":"MIN_MAX"}',
        ],
        policy_props={"chunk_size", "vision_backbone", "use_vae"},
        train_props={"steps", "batch_size", "peft"},
    )
    assert cfg == {
        "policy": {
            "chunk_size": 50,
            "vision_backbone": "resnet34",
            "use_vae": False,
            "normalization_mapping": {"STATE": "MIN_MAX"},
        },
        "train": {"steps": 300, "batch_size": 4, "peft": {"r": 8}, "seed": None},
    }
    assert parse_value("0.5") == 0.5 and parse_value("abc") == "abc" and parse_value("[1,2]") == [1, 2]
    for bad, msg in [
        ("nokey", "key=value"),
        ("=1", "key=value"),
        ("zzz=1", "unknown option"),
        ("train.steps.x=1", None),
    ]:
        with pytest.raises(OverrideError) as ei:
            build_config(
                ["train.steps=1", bad] if bad.startswith("train.steps.") else [bad],
                policy_props={"a"},
                train_props={"steps"},
            )
        if msg:
            assert msg in str(ei.value)
    with pytest.raises(OverrideError, match="both"):
        build_config(["seed=1"], policy_props={"seed"}, train_props={"seed"})
    with pytest.raises(OverrideError, match="prefix"):
        build_config(["steps=1"])


def test_state_dirs_follow_env(isolated_dirs: Path) -> None:
    from hibiscus.config import config_dir, state_dir

    assert config_dir() == isolated_dirs / "config" and state_dir() == isolated_dirs / "state"
