"""Fast tests: normalization.json, policy info, manifest/zip, logs, run_on_robot.sh, model card, types."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from export.logs import MetricRow, collapse_tqdm, write_metrics_csv, write_train_log
from export.manifest import copy_tree_exact, file_entries, sha256_file, verify_zip, write_manifest, zip_bundle
from export.model_card import CardContext, config_diff, hub_readme, render_model_card
from export.normalization import NormalizationError, build_normalization
from export.policy_info import chunk_and_steps, load_policy_info
from export.run_on_robot import CameraSpec, map_robot_type, render_run_on_robot
from export.tests.checkpoints import ACT_CHECKPOINT
from export.tests.conftest import REPO_ROOT, requires_act, validate
from export.types import ExportOptions, bundle_name, default_model_name, is_verified

EXAMPLES = REPO_ROOT / "docs" / "spec" / "examples"


# ---------------------------------------------------------------------------- normalization
@requires_act
def test_normalization_matches_spec_example_exactly() -> None:
    info = load_policy_info(ACT_CHECKPOINT)
    doc = build_normalization(ACT_CHECKPOINT, info)
    expected = json.loads((EXAMPLES / "normalization.example.json").read_text())
    assert doc == expected
    validate(doc, "normalization.schema.json")


@requires_act
def test_normalization_missing_stat_raises(tmp_path: Path) -> None:
    copy_tree_exact(ACT_CHECKPOINT, tmp_path)
    pre = json.loads((tmp_path / "policy_preprocessor.json").read_text())
    pre["steps"][-1]["config"]["norm_map"]["STATE"] = "QUANTILE10"
    (tmp_path / "policy_preprocessor.json").write_text(json.dumps(pre))
    info = load_policy_info(tmp_path)
    doc = build_normalization(tmp_path, info)  # q10/q90 exist in lerobot stats
    assert doc["features"]["observation.state"]["mode"] == "QUANTILE10"
    assert set(doc["features"]["observation.state"]) == {"type", "mode", "q10", "q90"}
    pre["steps"][-1]["config"]["norm_map"]["STATE"] = "BOGUS"
    (tmp_path / "policy_preprocessor.json").write_text(json.dumps(pre))
    with pytest.raises(NormalizationError):
        build_normalization(tmp_path, info)


@requires_act
def test_policy_info_act() -> None:
    info = load_policy_info(ACT_CHECKPOINT)
    assert info.policy_type == "act"
    assert info.onnx_support == "full"
    assert info.image_keys == ["observation.images.wrist_cam"]
    assert info.state is not None and info.state.shape == (6,)
    assert info.env_state is None
    assert info.action.shape == (6,)
    assert (info.chunk_size, info.n_action_steps) == (100, 100)
    assert info.peft is None


def test_chunk_and_steps_per_policy() -> None:
    assert chunk_and_steps({"type": "diffusion", "horizon": 16, "n_action_steps": 8}) == (16, 8)
    assert chunk_and_steps({"type": "vqbet", "action_chunk_size": 5}) == (5, 5)
    assert chunk_and_steps({"type": "tdmpc", "horizon": 5, "n_action_steps": 1}) == (5, 1)
    assert chunk_and_steps({"type": "pi0", "chunk_size": 50, "n_action_steps": 50}) == (50, 50)
    assert chunk_and_steps({"type": "smolvla"}) == (None, None)


# ---------------------------------------------------------------------------- names / gate
def test_bundle_and_model_names() -> None:
    assert default_model_name("so101_picknplace_20261114", "act") == "so101_picknplace_20261114_act"
    assert default_model_name("My Dataset!!", "diffusion") == "my_dataset_diffusion"
    long = default_model_name("x" * 200, "vqbet")
    assert len(long) <= 64 and long.endswith("_vqbet")
    assert default_model_name("___", "act") == "model_act"
    assert bundle_name("so101_picknplace_act", 42, 10000) == "so101_picknplace_act-r42-step10000"
    with pytest.raises(ValueError):
        ExportOptions(model_name="Bad Name")
    with pytest.raises(ValueError):
        ExportOptions.model_validate({"onnx": True, "unknown": 1})


@pytest.mark.parametrize(
    ("load_ok", "manifest_ok", "parity_ok", "support", "requested", "expected"),
    [
        (True, True, True, "full", True, True),
        (True, True, False, "full", True, False),
        (True, True, None, "full", True, False),
        (True, True, None, "full", False, True),
        (True, True, None, "none", True, True),
        (False, True, True, "full", True, False),
        (True, False, True, "split", True, False),
    ],
)
def test_verified_gate(
    load_ok: bool, manifest_ok: bool, parity_ok: bool | None, support: str, requested: bool, expected: bool
) -> None:
    assert (
        is_verified(
            load_ok=load_ok,
            manifest_ok=manifest_ok,
            parity_ok=parity_ok,
            onnx_support=support,
            onnx_requested=requested,
        )
        is expected
    )


# ---------------------------------------------------------------------------- manifest / zip
def _make_bundle(root: Path) -> Path:
    b = root / "demo_act-r1-step5"
    (b / "pretrained_model").mkdir(parents=True)
    (b / "pretrained_model" / "model.safetensors").write_bytes(os.urandom(4096))
    (b / "pretrained_model" / "config.json").write_text('{"type": "act"}')
    (b / "onnx").mkdir()
    (b / "onnx" / "infer_onnx.py").write_text("print('x')\n")
    (b / "Z.txt").write_text("upper-case sorts first bytewise")
    (b / "run_on_robot.sh").write_text("#!/usr/bin/env bash\n")
    write_manifest(b, {"schema_version": "1", "bundle_name": b.name})
    return b


def test_manifest_sorted_bytewise_and_excludes_itself(tmp_path: Path) -> None:
    b = _make_bundle(tmp_path)
    manifest = json.loads((b / "MANIFEST.json").read_text())
    paths = [f["path"] for f in manifest["files"]]
    assert paths == sorted(paths, key=lambda s: s.encode())
    assert paths[0] == "Z.txt"
    assert "MANIFEST.json" not in paths
    entry = next(f for f in manifest["files"] if f["path"] == "pretrained_model/model.safetensors")
    assert entry["size"] == 4096
    assert entry["sha256"] == sha256_file(b / "pretrained_model" / "model.safetensors")


def test_zip_layout_and_verify_roundtrip(tmp_path: Path) -> None:
    b = _make_bundle(tmp_path)
    zpath = tmp_path / "out" / f"{b.name}.zip"
    digest = zip_bundle(b, zpath, date_time=datetime(2026, 11, 15, tzinfo=UTC))
    assert digest == sha256_file(zpath)
    with zipfile.ZipFile(zpath) as zf:
        infos = {i.filename: i for i in zf.infolist()}
    assert all(n.startswith(f"{b.name}/") for n in infos)
    st = infos[f"{b.name}/pretrained_model/model.safetensors"]
    assert st.compress_type == zipfile.ZIP_STORED
    assert infos[f"{b.name}/pretrained_model/config.json"].compress_type == zipfile.ZIP_DEFLATED
    assert stat.S_IMODE(infos[f"{b.name}/run_on_robot.sh"].external_attr >> 16) == 0o755
    assert stat.S_IMODE(infos[f"{b.name}/onnx/infer_onnx.py"].external_attr >> 16) == 0o755
    assert stat.S_IMODE(infos[f"{b.name}/MANIFEST.json"].external_attr >> 16) == 0o644
    check = verify_zip(zpath, expected_name=b.name)
    assert check.ok, check.detail
    assert check.n_files == 5  # MANIFEST.json itself is not listed
    assert not verify_zip(zpath, expected_name="other-r1-step1").ok


def _rezip(
    src: Path, dst: Path, mutate: dict[str, bytes | None], add: dict[str, bytes] | None = None
) -> None:
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            if info.filename in mutate:
                data = mutate[info.filename]
                if data is None:
                    continue
                zout.writestr(info, data)
            else:
                zout.writestr(info, zin.read(info.filename))
        for name, data in (add or {}).items():
            zout.writestr(name, data)


def test_verify_detects_tamper_missing_extra_and_traversal(tmp_path: Path) -> None:
    b = _make_bundle(tmp_path)
    zpath = tmp_path / "b.zip"
    zip_bundle(b, zpath)
    n = b.name
    cases: dict[str, tuple[dict[str, bytes | None], dict[str, bytes] | None]] = {
        "tamper": ({f"{n}/pretrained_model/config.json": b'{"type": "evil"}'}, None),
        "missing": ({f"{n}/Z.txt": None}, None),
        "extra": ({}, {f"{n}/extra.bin": b"x"}),
        "traversal": ({}, {f"{n}/../evil.txt": b"x"}),
        "two_tops": ({}, {"other/file.txt": b"x"}),
        "no_manifest": ({f"{n}/MANIFEST.json": None}, None),
    }
    for label, (mutate, add) in cases.items():
        bad = tmp_path / f"{label}.zip"
        _rezip(zpath, bad, mutate, add)
        result = verify_zip(bad)
        assert not result.ok, label
        assert result.detail


def test_symlinks_rejected(tmp_path: Path) -> None:
    b = _make_bundle(tmp_path)
    (b / "link").symlink_to(b / "Z.txt")
    with pytest.raises(ValueError, match="symlink"):
        file_entries(b)


@requires_act
def test_copy_tree_exact_is_byte_identical(tmp_path: Path) -> None:
    copy_tree_exact(ACT_CHECKPOINT, tmp_path / "pm")
    src = {p.name: sha256_file(p) for p in ACT_CHECKPOINT.iterdir()}
    dst = {p.name: sha256_file(p) for p in (tmp_path / "pm").iterdir()}
    assert src == dst
    example = json.loads((EXAMPLES / "MANIFEST.example.json").read_text())
    for f in example["files"]:
        rel = f["path"].removeprefix("pretrained_model/")
        assert dst[rel] == f["sha256"]


# ---------------------------------------------------------------------------- logs
def test_collapse_tqdm_keeps_last_frame() -> None:
    raw = "INFO start\nTraining:  1%| 1/100\rTraining:  2%| 2/100\rTraining:  3%| 3/100\n\x1b[2Kdone\n\n"
    assert collapse_tqdm(raw) == "INFO start\nTraining:  3%| 3/100\ndone\n"
    assert collapse_tqdm("") == ""


def test_real_log_collapses(tmp_path: Path) -> None:
    import gzip

    fixture = REPO_ROOT / "worker" / "train" / "tests" / "fixtures" / "act_picknplace.log.gz"
    raw = tmp_path / "attempt1.log"
    raw.write_bytes(gzip.decompress(fixture.read_bytes()))
    second = tmp_path / "attempt2.log"
    second.write_text("resumed\rresumed 2\n")
    out = tmp_path / "logs" / "train.log"
    write_train_log([raw, second], out)
    text = out.read_text()
    assert "\r" not in text
    assert text.count("===== Hibiscus attempt") == 2
    assert "Checkpoint policy after step 10000" in text
    assert len(text) < raw.stat().st_size / 10  # tqdm frames dropped
    write_train_log([], tmp_path / "empty.log")
    assert (tmp_path / "empty.log").read_text().startswith("(no training log")


def test_metrics_csv(tmp_path: Path) -> None:
    ts = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)
    rows = [MetricRow(200, "loss", 0.5, ts), MetricRow(100, "loss", 1.25, ts), MetricRow(100, "lr", 1e-5, ts)]
    n = write_metrics_csv(rows, tmp_path / "m.csv")
    assert n == 3
    lines = (tmp_path / "m.csv").read_text().splitlines()
    assert lines[0] == "step,key,value,ts"
    assert lines[1] == "100,loss,1.25,2026-11-15T10:00:00+00:00"
    assert lines[2].startswith("100,lr,1e-05,")


# ---------------------------------------------------------------------------- run_on_robot.sh
CAM = [
    CameraSpec("observation.images.wrist_cam", 640, 360),
    CameraSpec("observation.images.front", 1280, 720),
]


def test_run_on_robot_template(tmp_path: Path) -> None:
    script = render_run_on_robot(
        bundle_name="so101_picknplace_act-r42-step10000",
        robot_type="so_follower",
        fps=30,
        cameras=CAM,
        task="pick and place",
    )
    assert script.startswith("#!/usr/bin/env bash\n")
    assert "lerobot-rollout" in script and "--strategy.type=base" in script
    assert '--policy.path="$HERE/pretrained_model"' in script
    assert "--robot.type=so101_follower" in script
    assert 'WRIST_CAM="${WRIST_CAM:-0}"' in script and 'FRONT="${FRONT:-1}"' in script
    assert (
        "wrist_cam: {type: opencv, index_or_path: ${WRIST_CAM}, width: 640, height: 360, fps: 30}" in script
    )
    assert "front: {type: opencv, index_or_path: ${FRONT}, width: 1280, height: 720, fps: 30}" in script
    assert "--task='pick and place'" in script
    assert "#   --strategy.type=episodic" in script and "--dataset.single_task='pick and place'" in script
    assert "\n# lerobot-record" not in script  # lerobot-record 0.7.1 has no --policy.path
    assert "TODO" not in script
    path = tmp_path / "run_on_robot.sh"
    path.write_text(script)
    subprocess.run(["bash", "-n", str(path)], check=True)  # noqa: S603, S607


def test_run_on_robot_quotes_hostile_metadata(tmp_path: Path) -> None:
    script = render_run_on_robot(
        bundle_name="x-r1-step1",
        robot_type="weird'; rm -rf / #",
        fps=29.97,
        cameras=CAM[:1],
        task="it's $(touch /tmp/pwned) `id`",
    )
    assert "# TODO(user): verify --robot.type" in script
    assert "--fps=29.97" in script
    path = tmp_path / "s.sh"
    path.write_text(script)
    subprocess.run(["bash", "-n", str(path)], check=True)  # noqa: S603, S607
    # Execute the argument lines with a fake lerobot-rollout that just prints its argv.
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "lerobot-rollout").write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@"\n')
    (fake / "lerobot-rollout").chmod(0o755)
    env = {"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path)}
    out = subprocess.run(  # noqa: S603
        ["bash", str(path)],  # noqa: S607
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert "--task=it's $(touch /tmp/pwned) `id`" in out
    assert "--robot.type=weird'; rm -rf / #" in out
    assert not Path("/tmp/pwned").exists()  # noqa: S108


def test_run_on_robot_rejects_unsafe_camera_and_bad_values() -> None:
    with pytest.raises(ValueError, match="camera name"):
        render_run_on_robot(
            bundle_name="b",
            robot_type=None,
            fps=30,
            cameras=[CameraSpec('observation.images.a"; id; "', 1, 1)],
            task="t",
        )
    with pytest.raises(ValueError, match="fps"):
        render_run_on_robot(bundle_name="b", robot_type=None, fps=0, cameras=[], task="t")
    with pytest.raises(ValueError, match="invalid size"):
        render_run_on_robot(
            bundle_name="b",
            robot_type=None,
            fps=30,
            cameras=[CameraSpec("observation.images.a", 0, 1)],
            task="t",
        )


def test_robot_type_mapping() -> None:
    assert map_robot_type("so_follower") == ("so101_follower", True)
    assert map_robot_type("so100_follower") == ("so100_follower", True)
    assert map_robot_type("koch_follower") == ("koch_follower", True)
    assert map_robot_type("aloha") == ("aloha", False)
    assert map_robot_type(None) == ("so101_follower", False)
    no_cam = render_run_on_robot(bundle_name="b", robot_type="koch_follower", fps=15, cameras=[], task="t")
    assert "--robot.cameras" not in no_cam


# ---------------------------------------------------------------------------- model card
def _card(**kw: object) -> CardContext:
    base: dict[str, object] = dict(
        bundle_name="d_act-r1-step10",
        policy_type="act",
        dataset_name="d",
        dataset_version=2,
        dataset_repo_id="local/d",
        dataset_content_hash="a" * 64,
        checkpoint_step=10,
        verified=True,
        load_ok=True,
        parity_ok=True,
        onnx_status="passed",
        onnx_support="full",
        run_name="r",
        run_number=1,
        seed=1,
        total_steps=10,
        batch_size=8,
        mixed_precision="no",
        gpu_name="RTX 3060",
        gpu_seconds=3725.0,
        heldout_episodes=[3],
        train_episodes=[0, 1, 2],
        final_loss=0.25,
        software={"lerobot": "0.7.1"},
        config={"type": "act", "chunk_size": 50, "dim_model": 512, "input_features": {}},
        config_defaults={"chunk_size": 100, "dim_model": 512},
        eval_metrics=None,
        parity_report=None,
        fps=30.0,
        tasks=["pick"],
    )
    base.update(kw)
    return CardContext(**base)  # type: ignore[arg-type]


def test_model_card_sections_and_diff() -> None:
    md = render_model_card(_card())
    for heading in (
        "## Summary",
        "## Intended use & limitations",
        "## Training",
        "## Results",
        "## How to run",
        "## Reproducibility",
        "## Files",
    ):
        assert heading in md
    assert "_Tóm tắt_" in md and "không phải tỉ lệ thành công" in md
    assert "| `chunk_size` | 50 | 100 |" in md
    assert "dim_model" not in md.split("## Results")[0].split("default |")[1]
    assert "1h 02m 05s" in md
    assert "**verified**" in md and "infer_onnx.py" in md
    md2 = render_model_card(
        _card(verified=False, parity_ok=None, onnx_status="not_supported", final_loss=None)
    )
    assert "**not verified**" in md2 and "infer_onnx.py" not in md2 and "Final loss: n/a" in md2


def test_config_diff_without_defaults_lists_all() -> None:
    rows = config_diff({"a": 1, "type": "act", "device": "cuda"}, None)
    assert rows == [("a", 1, "—")]


def test_hub_readme_front_matter() -> None:
    out = hub_readme("# card\n", policy_type="act", dataset_repo_id="user/ds")
    assert out.startswith(
        "---\nlibrary_name: lerobot\ntags:\n- lerobot\n- act\n- robotics\ndatasets:\n- user/ds\n---\n"
    )
    assert "datasets:" not in hub_readme("# c", policy_type="act", dataset_repo_id=None)
