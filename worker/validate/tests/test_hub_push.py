"""``push_model_hub`` CPU job (QC-backend-02) with fake DB / object store / Hub API."""

from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path
from typing import Any

import pytest

from validate import db as dbm
from validate import hub_push as hp
from validate.runner import Runner
from validate.settings import WorkerSettings


def _bundle_zip(tmp: Path, name: str = "m_act-r1-step10") -> Path:
    root = tmp / "src" / name
    (root / "pretrained_model").mkdir(parents=True)
    (root / "pretrained_model" / "config.json").write_text(json.dumps({"type": "act"}))
    (root / "pretrained_model" / "model.safetensors").write_bytes(b"\0" * 16)
    (root / "onnx").mkdir()
    (root / "onnx" / "model.onnx").write_bytes(b"onnx")
    (root / "MODEL_CARD.md").write_text("# card\n")
    (root / "MANIFEST.json").write_text("{}")
    z = tmp / f"{name}.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(root.parent).as_posix())
    return z


class FakeDb:
    def __init__(self, model: dict[str, Any] | None) -> None:
        self.model = model
        self.finished: list[tuple[Any, ...]] = []
        self.pushed: list[tuple[Any, str]] = []
        self.engine: Any = None

    def get_model(self, model_id: uuid.UUID) -> dict[str, Any] | None:
        return self.model

    def mark_pushed(self, model_id: uuid.UUID, repo_id: str) -> None:
        self.pushed.append((model_id, repo_id))

    def finish(
        self, job_id: uuid.UUID, status: str, result: Any = None, code: Any = None, msg: Any = None
    ) -> bool:
        self.finished.append((status, result, code, msg))
        return True

    def requeue(self, *a: Any) -> bool:
        self.finished.append(("requeued", *a))
        return True

    def heartbeat(self, *a: Any) -> bool:
        return True


class FakeStore:
    def __init__(self, zip_path: Path) -> None:
        self.zip_path = zip_path
        self.calls: list[tuple[str, str]] = []

    def download(self, bucket: str, key: str, dest: Path) -> None:
        self.calls.append((bucket, key))
        dest.write_bytes(self.zip_path.read_bytes())


class FakeApi:
    def __init__(self, token: str, log: list[Any]) -> None:
        self.token = token
        self.log = log

    def create_repo(self, repo_id: str, **kw: Any) -> None:
        self.log.append(("create_repo", repo_id, kw))

    def upload_folder(self, *, folder_path: str, repo_id: str, **kw: Any) -> Any:
        files = sorted(
            p.relative_to(folder_path).as_posix() for p in Path(folder_path).rglob("*") if p.is_file()
        )
        self.log.append(("upload_folder", repo_id, files, self.token))
        return type("Commit", (), {"commit_url": f"https://huggingface.co/{repo_id}/commit/abc"})()


def _job(payload: dict[str, Any], model_id: uuid.UUID) -> dbm.JobRow:
    return dbm.JobRow(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        kind="push_model_hub",
        payload=payload,
        attempts=1,
        max_attempts=2,
        dataset_version_id=None,
        created_by=uuid.uuid4(),
        model_id=model_id,
    )


def _runner(tmp_path: Path, db: FakeDb, store: FakeStore) -> Runner:
    s = WorkerSettings(
        database_url="postgresql+psycopg://x@localhost/x",
        s3_endpoint_url="http://localhost:1",
        s3_access_key="a",
        s3_secret_key="b",  # noqa: S106 - fake
        work_dir=tmp_path / "work",
        heartbeat_s=0.05,
    )
    return Runner(s, db, store)  # type: ignore[arg-type]


@pytest.mark.parametrize("include_onnx", [False, True])
def test_push_model_hub_uploads_policy_and_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, include_onnx: bool
) -> None:
    mid = uuid.uuid4()
    model = {
        "id": mid,
        "name": "m_act-r1-step10",
        "policy_type": "act",
        "status": "ready",
        "bundle_uri": f"s3://hibiscus-artifacts/models/{mid}/m_act-r1-step10.zip",
        "deleted_at": None,
    }
    db, store = FakeDb(model), FakeStore(_bundle_zip(tmp_path))
    log: list[Any] = []
    monkeypatch.setattr(Runner, "_hf_token", lambda self, user: "hf_secret")
    real_push = hp.push
    monkeypatch.setattr(
        hp,
        "push",
        lambda folder, req, **kw: real_push(folder, req, **kw, api_factory=lambda t: FakeApi(t, log)),
    )
    r = _runner(tmp_path, db, store)
    r.process(_job({"repo_id": "me/my-policy", "private": True, "include_onnx": include_onnx}, mid))
    assert db.finished[-1][0] == "succeeded", db.finished
    assert db.pushed == [(mid, "me/my-policy")]
    assert store.calls == [("hibiscus-artifacts", f"models/{mid}/m_act-r1-step10.zip")]
    create, upload = log
    assert create == (
        "create_repo",
        "me/my-policy",
        {"repo_type": "model", "private": True, "exist_ok": True},
    )
    files = upload[2]
    assert {"config.json", "model.safetensors", "README.md", "MANIFEST.json"} <= set(files)
    assert ("onnx/model.onnx" in files) is include_onnx
    assert upload[3] == "hf_secret"


def test_push_model_hub_refuses_without_token_or_ready_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mid = uuid.uuid4()
    store = FakeStore(_bundle_zip(tmp_path))
    monkeypatch.setattr(Runner, "_hf_token", lambda self, user: None)
    db = FakeDb(
        {"id": mid, "name": "x", "policy_type": "act", "status": "ready", "bundle_uri": "s3://b/k.zip"}
    )
    _runner(tmp_path, db, store).process(_job({"repo_id": "me/x"}, mid))
    assert db.finished[-1][0] == "failed" and db.finished[-1][2] == "hf_token_missing"
    db2 = FakeDb({"id": mid, "name": "x", "policy_type": "act", "status": "building", "bundle_uri": None})
    _runner(tmp_path, db2, store).process(_job({"repo_id": "me/x"}, mid))
    assert db2.finished[-1][2] == "model_not_ready"
    db3 = FakeDb(None)
    _runner(tmp_path, db3, store).process(_job({"repo_id": "../../etc"}, mid))
    assert db3.finished[-1][2] == "hub_repo_invalid"


def test_extract_bundle_rejects_traversal(tmp_path: Path) -> None:
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("b/pretrained_model/config.json", "{}")
        zf.writestr("b/../../escape.txt", "x")
    with pytest.raises(hp.HubPushError):
        hp.extract_bundle(z, tmp_path / "out")
