"""End-to-end ``build_bundle`` on real LeRobot checkpoints + the golden dataset (CPU)."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from export.bundle import build_bundle
from export.logs import MetricRow
from export.manifest import sha256_file
from export.tests.checkpoints import (
    ACT_CHECKPOINT,
    GOLDEN_DATASET,
    GOLDEN_REPO_ID,
    LELAB_PYTHON,
    TRAIN_LOG,
    make_random_checkpoint,
)
from export.tests.conftest import REPO_ROOT, requires_act, requires_golden, validate
from export.types import BundleRequest, DatasetInfo, ExportOptions, RunInfo, TrainingInfo

pytestmark = requires_golden

TS = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)


def _request(
    ckpt: Path,
    work: Path,
    *,
    heldout: list[int],
    options: ExportOptions,
    step: int = 300,
    python: str | None = None,
    logs: list[Path] | None = None,
) -> BundleRequest:
    return BundleRequest(
        model_id="00000000-0000-4000-8000-000000000001",
        run=RunInfo(
            id="00000000-0000-4000-8000-000000000002",
            number=42,
            name="golden",
            workspace_id="00000000-0000-4000-8000-000000000003",
        ),
        dataset=DatasetInfo(
            dataset_id="00000000-0000-4000-8000-000000000004",
            version_id="00000000-0000-4000-8000-000000000005",
            version=1,
            name="so101_picknplace_20261114",
            content_hash="ab" * 32,
            repo_id=GOLDEN_REPO_ID,
            root=GOLDEN_DATASET,
        ),
        training=TrainingInfo(
            seed=1000,
            total_steps=step,
            batch_size=8,
            mixed_precision="no",
            gpu_name="NVIDIA GeForce RTX 3060",
            heldout_episodes=heldout,
            train_episodes=[e for e in range(20) if e not in heldout],
            gpu_seconds=12.5,
            final_loss=0.5,
        ),
        pretrained_dir=ckpt,
        checkpoint_step=step,
        work_dir=work,
        options=options,
        train_logs=logs or [],
        metrics=[MetricRow(100, "loss", 1.0, TS), MetricRow(200, "loss", 0.7, TS)],
        image_digest="sha256:" + "1" * 64,
        created_at=TS,
        load_check_python=python,
        parity_samples=4,
    )


def _tree(bundle_dir: Path) -> set[str]:
    return {p.relative_to(bundle_dir).as_posix() for p in bundle_dir.rglob("*") if p.is_file()}


PM = {
    "pretrained_model/config.json",
    "pretrained_model/model.safetensors",
    "pretrained_model/policy_preprocessor.json",
    "pretrained_model/policy_preprocessor_step_3_normalizer_processor.safetensors",
    "pretrained_model/policy_postprocessor.json",
    "pretrained_model/policy_postprocessor_step_0_unnormalizer_processor.safetensors",
}
COMMON = {"logs/train.log", "logs/metrics.csv", "run_on_robot.sh", "MODEL_CARD.md", "MANIFEST.json"}
ONNX_FULL = {
    "onnx/model.onnx",
    "onnx/io_spec.json",
    "onnx/normalization.json",
    "onnx/parity_report.json",
    "onnx/infer_onnx.py",
    "onnx/requirements.txt",
}


def test_build_bundle_small_act_verified(small_act: Path, tmp_path: Path) -> None:
    req = _request(small_act, tmp_path, heldout=[19], options=ExportOptions(onnx_fp16=True))
    res = build_bundle(req)
    assert res.bundle_name == "so101_picknplace_20261114_act-r42-step300"
    assert res.verified, res.verification.details
    assert res.onnx_status == "passed" and res.api_onnx_status == "passed"
    v = res.verification
    assert v.load_ok and v.parity_ok and v.manifest_ok and v.details is None
    assert v.parity is not None and v.parity["n_samples"] == 4 and v.parity["max_abs_diff"] < 1e-4

    tree = _tree(res.bundle_dir)
    eval_files = {"eval/metrics.json", "eval/plots/per_joint_mae.png", "eval/plots/episode_019.png"}
    assert tree == PM | COMMON | ONNX_FULL | {"onnx/model.fp16.onnx"} | eval_files

    manifest = json.loads((res.bundle_dir / "MANIFEST.json").read_text())
    validate(manifest, "manifest.schema.json")
    assert manifest == res.manifest
    em = res.eval_metrics
    assert em is not None
    assert manifest["checks"] == {
        "load_ok": True,
        "lelab_compatible": True,
        "lelab_check": "emulated",
        "lelab_requirements": [],
        "parity_ok": True,
        "onnx_status": "passed",
        "eval": {"action_mae": em["overall"]["mae"], "action_mse": em["overall"]["mse"]},
    }
    assert manifest["policy"] == {
        "type": "act",
        "onnx_support": "full",
        "chunk_size": 10,
        "n_action_steps": 5,
        "peft": None,
    }
    ds = manifest["dataset"]
    assert ds["robot_type"] == "so_follower" and ds["fps"] == 30.0
    assert ds["camera_keys"] == ["observation.images.wrist_cam"]
    assert ds["tasks"] == ["Pick the blue cube and place on top the white cube"]
    assert manifest["software"]["lerobot"] == "0.7.1"
    assert manifest["created_at"] == "2026-11-15T10:00:00Z"
    for f in manifest["files"]:
        if f["path"].startswith("pretrained_model/"):
            assert f["sha256"] == sha256_file(small_act / f["path"].removeprefix("pretrained_model/"))

    assert res.zip_path.name == f"{res.bundle_name}.zip" and res.zip_sha256 == sha256_file(res.zip_path)
    with zipfile.ZipFile(res.zip_path) as zf:
        assert {n.split("/", 1)[0] for n in zf.namelist()} == {res.bundle_name}
    assert res.eval_summary is not None and set(res.eval_summary) == {"action_mae", "action_mse"}
    assert (res.bundle_dir / "logs" / "metrics.csv").read_text().splitlines()[1].startswith("100,loss,1.0,")
    script = (res.bundle_dir / "run_on_robot.sh").read_text()
    assert "--robot.type=so101_follower" in script and "width: 640, height: 360, fps: 30" in script
    card = (res.bundle_dir / "MODEL_CARD.md").read_text()
    assert "**verified**" in card and "| `chunk_size` | 10 | 100 |" in card
    for k in ("onnx_s", "eval_s", "load_check_s", "zip_s", "verify_zip_s", "total_s"):
        assert res.timings[k] >= 0

    # the shipped infer_onnx.py self-test runs from the bundle, in an isolated interpreter
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-I", str(res.bundle_dir / "onnx" / "infer_onnx.py"), "--selftest"],
        capture_output=True,
        text=True,
        check=True,
        cwd=res.bundle_dir,
    )
    assert json.loads(out.stdout.strip().splitlines()[-1])["policy_type"] == "act"


def test_build_bundle_onnx_skipped_no_heldout(small_act: Path, tmp_path: Path) -> None:
    req = _request(
        small_act, tmp_path, heldout=[], options=ExportOptions(onnx=False, model_name="custom-name")
    )
    res = build_bundle(req)
    assert res.bundle_name == "custom-name-r42-step300"
    assert res.onnx_status == "skipped" and res.api_onnx_status == "not_supported"
    assert res.verified  # parity not required when ONNX was not requested (spec §10)
    assert res.verification.parity_ok is None and res.parity_report is None and res.eval_metrics is None
    assert _tree(res.bundle_dir) == PM | COMMON
    validate(res.manifest, "manifest.schema.json")
    assert res.manifest["checks"]["eval"] is None


def test_build_bundle_diffusion_split(small_diffusion: Path, tmp_path: Path) -> None:
    res = build_bundle(_request(small_diffusion, tmp_path, heldout=[19], options=ExportOptions(eval=False)))
    assert res.verified, res.verification.details
    assert res.onnx_status == "passed"
    tree = _tree(res.bundle_dir)
    assert {"onnx/obs_encoder.onnx", "onnx/denoiser.onnx"} <= tree and "onnx/model.onnx" not in tree
    validate(res.manifest, "manifest.schema.json")
    assert res.manifest["policy"]["onnx_support"] == "split"
    # QC-ml-1: LeLab's venv has no diffusers, so the bundle is verified (LeRobot 0.7.1 loads it)
    # but not LeLab-compatible, and the card / script / MANIFEST say what to install.
    checks = res.manifest["checks"]
    assert checks["load_ok"] is True and checks["lelab_compatible"] is False
    assert checks["lelab_requirements"] == ["diffusers>=0.38.0,<0.40.0"]
    assert res.verification.lelab_compatible is False
    assert res.verification.to_json()["lelab_compatible"] is False
    assert "diffusers" in (res.verification.details or "")
    card = (res.bundle_dir / "MODEL_CARD.md").read_text()
    assert "LeRobot load: ok" not in card
    assert "LeLab venv: **needs extra packages**" in card
    assert "pip install 'diffusers>=0.38.0,<0.40.0'" in card
    script = (res.bundle_dir / "run_on_robot.sh").read_text()
    assert "import diffusers;" in script and "pip install 'diffusers>=0.38.0,<0.40.0'" in script
    assert res.manifest["policy"]["chunk_size"] == 16 and res.manifest["policy"]["n_action_steps"] == 8


def test_build_bundle_not_supported_policy(tmp_path: Path) -> None:
    """A policy without ONNX in v1 (TD-MPC) still gets a verified bundle: load + manifest only."""
    ckpt = make_random_checkpoint(
        "tdmpc", tmp_path / "tdmpc" / "pretrained_model", state_only=True, horizon=2
    )
    res = build_bundle(_request(ckpt, tmp_path / "work", heldout=[19], options=ExportOptions(eval=False)))
    assert res.onnx_status == "not_supported" and res.onnx_detail
    assert res.verification.parity_ok is None
    assert not any(p.startswith("onnx/") for p in _tree(res.bundle_dir))
    validate(res.manifest, "manifest.schema.json")
    assert res.manifest["policy"]["onnx_support"] == "none"
    assert res.verification.load_ok, res.verification.details
    assert res.verification.manifest_ok and res.verified
    assert "--robot.cameras" not in (res.bundle_dir / "run_on_robot.sh").read_text()


def test_tampered_checkpoint_load_fails(small_act: Path, tmp_path: Path) -> None:
    import shutil

    bad = tmp_path / "bad"
    shutil.copytree(small_act, bad)
    (bad / "model.safetensors").write_bytes(b"not a safetensors file")
    res = build_bundle(
        _request(bad, tmp_path / "w", heldout=[19], options=ExportOptions(onnx=False, eval=False))
    )
    assert not res.verification.load_ok and not res.verified
    assert res.manifest["checks"]["load_ok"] is False
    assert res.verification.details and res.verification.details.startswith("load:")


@pytest.mark.slow
@requires_act
def test_golden_act_checkpoint_bundle(tmp_path: Path) -> None:
    """The real 10k-step ACT checkpoint: full bundle incl. fp16, eval on held-out episodes 18-19,
    32 parity samples and a load check in the LeLab venv when available."""
    python = str(LELAB_PYTHON) if LELAB_PYTHON.is_file() else None
    req = _request(
        ACT_CHECKPOINT,
        tmp_path,
        heldout=[18, 19],
        options=ExportOptions(onnx_fp16=True),
        step=10000,
        python=python,
        logs=[TRAIN_LOG] if TRAIN_LOG.is_file() else [],
    )
    req.parity_samples = 32
    res = build_bundle(req)
    assert res.verified, res.verification.details
    report = res.parity_report
    assert report is not None and report["n_samples"] == 32 and report["sample_source"] == "heldout"
    model = next(g for g in report["graphs"] if g["comparison"] == "model")
    assert model["passed"] and model["max_abs_diff"] < 1e-4
    example = json.loads((REPO_ROOT / "docs/spec/examples/MANIFEST.example.json").read_text())
    got = {f["path"]: f["sha256"] for f in res.manifest["files"]}
    for f in example["files"]:
        assert got[f["path"]] == f["sha256"]
    print(
        json.dumps(
            {
                "parity": report,
                "eval": res.eval_metrics and res.eval_metrics["overall"],
                "timings": res.timings,
                "zip_size": res.zip_size,
            },
            indent=1,
        )
    )


def _script_args(script: str, marker: str, here: Path, comment: bool) -> list[str]:
    import shlex

    block = script.split(marker, 1)[1].split("\n\n", 1)[0]
    if comment:
        block = "\n".join(line.removeprefix("# ") for line in block.splitlines())
    for old, new in (
        ("$HERE", str(here)),
        ("${WRIST_CAM}", "0"),
        ('"$PORT"', "/dev/null"),
        ('"$ROBOT_ID"', "my_follower"),
        ('"${DURATION:-60}"', "60"),
    ):
        block = block.replace(old, new)
    return shlex.split(block.replace("\\\n", " "))


def test_run_on_robot_parses_with_lerobot_cli(small_act: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Both commands of the generated script are accepted by LeRobot 0.7.1's own CLI parser
    (parse only: no robot, camera or serial port is opened)."""
    import lerobot.scripts.lerobot_rollout  # noqa: F401  # registers robot/camera choices like the CLI
    from lerobot.configs import parser
    from lerobot.rollout.configs import RolloutConfig

    from export.bundle import dataset_meta
    from export.run_on_robot import CameraSpec, render_run_on_robot

    meta = dataset_meta(GOLDEN_DATASET, GOLDEN_REPO_ID)
    w, h = meta["camera_sizes"]["observation.images.wrist_cam"]
    script = render_run_on_robot(
        bundle_name="b-r1-step1",
        robot_type=meta["robot_type"],
        fps=meta["fps"],
        cameras=[CameraSpec("observation.images.wrist_cam", w, h)],
        task=meta["tasks"][0],
    )
    seen: list[RolloutConfig] = []

    def _capture(cfg: RolloutConfig) -> None:
        seen.append(cfg)

    _capture.__annotations__["cfg"] = RolloutConfig  # parser.wrap needs the class, not a string
    capture = parser.wrap()(_capture)

    for marker, comment in (("lerobot-rollout \\\n", False), ("# lerobot-rollout \\\n", True)):
        args = _script_args(script, marker, small_act.parent, comment)
        monkeypatch.setattr(sys, "argv", ["lerobot-rollout", *args])
        capture()
    base, episodic = seen
    for cfg in seen:
        assert type(cfg.robot).__name__ == "SOFollowerRobotConfig" and cfg.robot.port == "/dev/null"
        cam = cfg.robot.cameras["wrist_cam"]
        assert (cam.width, cam.height, cam.fps, cam.index_or_path) == (640, 360, 30, 0)
        assert cfg.policy is not None and cfg.policy.type == "act"
    assert type(base.strategy).__name__ == "BaseStrategyConfig"
    assert base.task == meta["tasks"][0] and base.fps == 30 and base.duration == 60
    assert type(episodic.strategy).__name__ == "EpisodicStrategyConfig"
    assert episodic.dataset is not None and episodic.dataset.single_task == meta["tasks"][0]
    assert episodic.dataset.repo_id == "local/eval_b-r1-step1" and episodic.dataset.push_to_hub is False


def test_cli_entrypoints(small_act: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``python -m export`` (manual builds) and the bundled ``infer_onnx.py`` CLI, in-process."""
    from export.__main__ import main as export_main
    from export.templates.infer_onnx import main as infer_main

    argv = ["--pretrained-dir", str(small_act), "--dataset-root", str(GOLDEN_DATASET)]
    argv += ["--repo-id", GOLDEN_REPO_ID, "--dataset-name", "golden", "--work-dir", str(tmp_path)]
    argv += ["--step", "7", "--heldout", "19", "--total-episodes", "20", "--no-eval", "--parity-samples", "2"]
    rc = export_main(argv)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["verified"] and out["bundle_name"] == "golden_act-r1-step7"
    bundle = tmp_path / out["bundle_name"]
    assert infer_main(["--bundle", str(bundle), "--selftest", "--steps", "6"]) == 0
    selftest = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert len(selftest["action"]) == 6
    assert infer_main(["--bundle", str(bundle)]) == 0
    assert json.loads(capsys.readouterr().out)["policy_type"] == "act"


def test_reverify_bundle_zip(small_act: Path, tmp_path: Path) -> None:
    """reverifyModel: the 3 checks re-run on the delivered zip; a tampered ONNX graph fails parity."""
    from export.verify import reverify_bundle

    res = build_bundle(_request(small_act, tmp_path, heldout=[19], options=ExportOptions(eval=False)))
    v, verified = reverify_bundle(
        res.zip_path, dataset_root=GOLDEN_DATASET, repo_id=GOLDEN_REPO_ID, heldout_episodes=[19], n_samples=3
    )
    assert verified and v.load_ok and v.manifest_ok and v.parity_ok, v.details
    assert v.parity is not None and v.parity["n_samples"] == 3

    # Swap the ONNX graph for one exported from a different (re-initialised) checkpoint, keep the
    # manifest consistent: parity must catch it even though hashes match.
    other = make_random_checkpoint("act", tmp_path / "other" / "pretrained_model", dim_feedforward=64)
    res2 = build_bundle(_request(other, tmp_path / "w2", heldout=[19], options=ExportOptions(eval=False)))
    bundle = res.bundle_dir
    (bundle / "onnx" / "model.onnx").write_bytes((res2.bundle_dir / "onnx" / "model.onnx").read_bytes())
    from export.manifest import write_manifest, zip_bundle

    manifest = json.loads((bundle / "MANIFEST.json").read_text())
    manifest.pop("files")
    write_manifest(bundle, manifest)
    bad_zip = tmp_path / "swapped.zip"
    zip_bundle(bundle, bad_zip)
    v2, verified2 = reverify_bundle(
        bad_zip, dataset_root=GOLDEN_DATASET, repo_id=GOLDEN_REPO_ID, heldout_episodes=[19], n_samples=2
    )
    assert v2.manifest_ok and v2.load_ok
    assert v2.parity_ok is False and not verified2
    assert v2.details is not None and "parity" in v2.details
