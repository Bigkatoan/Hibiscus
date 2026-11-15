from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path

import pytest

from hibiscus.api import HibiscusApi
from hibiscus.pull import Puller, PullError, verify_manifest
from tests.conftest import ACT_CHECKPOINT
from tests.fake_server import FakeHibiscus

BUNDLE = "so101_picknplace_act-r42-step300"


def _files() -> dict[str, bytes]:
    files = {
        "pretrained_model/model.safetensors": os.urandom(300_000),
        "pretrained_model/config.json": b'{"type": "act"}',
        "onnx/model.onnx": os.urandom(50_000),
        "run_on_robot.sh": b"#!/usr/bin/env bash\necho run\n",
        "MODEL_CARD.md": b"# card\n",
    }
    if ACT_CHECKPOINT.is_dir():  # use the real (small) LeRobot json files when available
        for name in (
            "config.json",
            "train_config.json",
            "policy_preprocessor.json",
            "policy_postprocessor.json",
        ):
            files[f"pretrained_model/{name}"] = (ACT_CHECKPOINT / name).read_bytes()
    return files


def test_pull_zip_verifies_manifest(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    files = _files()
    model = fake.add_model(files, bundle_name=BUNDLE)
    res = Puller(api).pull(model["id"], tmp_path / "models")
    bundle = tmp_path / "models" / BUNDLE
    assert res.bundle_dir == bundle and res.files_verified == len(files) and not res.skipped
    for rel, data in files.items():
        assert (bundle / rel).read_bytes() == data
    assert os.access(bundle / "run_on_robot.sh", os.X_OK)
    assert not (tmp_path / "models" / ".hibiscus-partial").exists()
    # second pull is a no-op (verified copy present)
    again = Puller(api).pull(model["id"], tmp_path / "models")
    assert again.skipped
    assert [r.operation_id for r in fake.requests].count("downloadModel") == 1


def test_pull_resumes_interrupted_download_with_range(
    fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path
) -> None:
    model = fake.add_model(_files(), bundle_name=BUNDLE)
    fake.download_drop_at = 100_000
    res = Puller(api).pull(model["id"], tmp_path)
    assert res.resumed_from == 0 and res.files_verified > 0
    dl = [r for r in fake.requests if r.operation_id == "downloadModel"]
    assert len(dl) == 2
    assert "range" not in dl[0].headers
    assert dl[1].headers["range"] == "bytes=100000-"
    assert dl[1].headers["if-range"] == f'"{model["bundle_sha256"]}"'


def test_pull_resume_across_processes(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    model = fake.add_model(_files(), bundle_name=BUNDLE)
    part = tmp_path / ".hibiscus-partial" / f"{model['id']}.zip.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(fake.model_zip[model["id"]][:12345])
    res = Puller(api).pull(model["id"], tmp_path)
    assert res.resumed_from == 12345
    assert res.bytes_downloaded == len(fake.model_zip[model["id"]]) - 12345


def test_pull_rejects_tampered_bundle(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    model = fake.add_model(_files(), bundle_name=BUNDLE, tamper="pretrained_model/config.json")
    with pytest.raises(PullError, match=r"sha256 mismatch: pretrained_model/config\.json|size mismatch"):
        Puller(api).pull(model["id"], tmp_path)
    assert not (tmp_path / BUNDLE).exists()


def test_pull_rejects_zip_sha_mismatch(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    model = fake.add_model(_files(), bundle_name=BUNDLE)
    fake.models[model["id"]]["bundle_sha256"] = "0" * 64
    with pytest.raises(PullError, match="bundle sha256 mismatch"):
        Puller(api).pull(model["id"], tmp_path)


def test_pull_only_pretrained_model(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    files = _files()
    model = fake.add_model(files, bundle_name=BUNDLE)
    res = Puller(api).pull(model["id"], tmp_path, only="pretrained_model")
    bundle = tmp_path / BUNDLE
    want = {k for k in files if k.startswith("pretrained_model/")}
    got = {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()}
    assert got == want | {"MANIFEST.json"}
    assert res.files_verified == len(want)
    assert [r.operation_id for r in fake.requests].count("downloadModel") == 0
    paths = {r.path for r in fake.requests if r.operation_id == "getModelFile"}
    assert f"/models/{model['id']}/files/pretrained_model%2Fconfig.json" in paths


def test_pull_model_not_ready(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    model = fake.add_model(_files())
    fake.models[model["id"]]["status"] = "building"
    with pytest.raises(PullError, match="not ready"):
        Puller(api).pull(model["id"], tmp_path)


def test_extract_rejects_traversal(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    model = fake.add_model(_files(), bundle_name=BUNDLE)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{BUNDLE}/../evil.txt", "x")
    import hashlib

    data = buf.getvalue()
    fake.model_zip[model["id"]] = data
    fake.models[model["id"]]["bundle_sha256"] = hashlib.sha256(data).hexdigest()
    fake.models[model["id"]]["bundle_size_bytes"] = len(data)
    with pytest.raises(PullError, match="unsafe path"):
        Puller(api).pull(model["id"], tmp_path / "dst")
    assert not (tmp_path / "evil.txt").exists()


def test_verify_manifest_detects_extra_and_missing(tmp_path: Path) -> None:
    (tmp_path / "a").write_bytes(b"1")
    (tmp_path / "extra").write_bytes(b"2")
    manifest = {
        "schema_version": "1",
        "bundle_name": "b",
        "files": [
            {
                "path": "a",
                "size": 1,
                "sha256": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
            },
            {"path": "missing", "size": 1, "sha256": "0" * 64},
        ],
    }
    (tmp_path / "MANIFEST.json").write_text(json.dumps(manifest))
    checked, problems = verify_manifest(tmp_path)
    assert checked == 1
    assert problems == ["missing: missing", "not in manifest: extra"]
    assert verify_manifest(tmp_path / "nope") == (0, ["MANIFEST.json missing"])
