"""SEC-input-1: processor allow-list and the ``init_from.hf_repo_id`` fetch (no network)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from core.child_env import child_env
from core.pretrained_guard import (
    ALLOWED_PROCESSOR_STEPS,
    UntrustedPretrainedError,
    validate_pretrained_dir,
    validate_processor_config,
)
from export.tests.checkpoints import ACT_CHECKPOINT, GOLDEN_DATASET, GOLDEN_REPO_ID
from export.tests.conftest import requires_act, requires_golden
from train import init_from
from train.init_from import HF_ALLOW_PATTERNS, InitFromError, fetch_hf_init

EVIL = {
    "name": "policy_preprocessor",
    "steps": [{"class": "subprocess.Popen", "config": {"args": ["sh", "-c", "id > PWNED"]}}],
}


def test_rejects_class_import_paths() -> None:
    with pytest.raises(UntrustedPretrainedError, match="'class'"):
        validate_processor_config(EVIL)
    # even a class path inside lerobot is refused: getattr() can return any re-exported callable
    doc = {"steps": [{"class": "lerobot.processor.pipeline.importlib.import_module", "config": {}}]}
    with pytest.raises(UntrustedPretrainedError):
        validate_processor_config(doc)


@pytest.mark.parametrize(
    "step",
    [
        {"registry_name": "reward_classifier_processor", "config": {}},  # registered, not allowed
        {"registry_name": "normalizer_processor", "config": [], "state_file": "x.safetensors"},
        {"registry_name": "normalizer_processor", "config": {}, "state_file": "../../etc/x.safetensors"},
        {"registry_name": "normalizer_processor", "config": {}, "extra": 1},
    ],
)
def test_rejects_unknown_steps_and_odd_entries(step: dict[str, Any]) -> None:
    with pytest.raises(UntrustedPretrainedError):
        validate_processor_config({"steps": [step]})


def test_allow_list_is_lerobot_processor_steps() -> None:
    import lerobot.policies.pi0.processor_pi0
    import lerobot.policies.pi05.processor_pi05
    import lerobot.policies.smolvla.processor_smolvla  # noqa: F401
    from lerobot.processor.pipeline import ProcessorStepRegistry

    for name in ALLOWED_PROCESSOR_STEPS:
        cls = ProcessorStepRegistry.get(name)
        assert cls.__module__.startswith(("lerobot.processor.", "lerobot.policies.")), (name, cls.__module__)


@pytest.mark.parametrize("fixture", ["small_act", "small_diffusion", "small_vqbet"])
def test_lerobot_generated_processors_pass(fixture: str, request: pytest.FixtureRequest) -> None:
    validate_pretrained_dir(request.getfixturevalue(fixture))


@requires_act
def test_real_checkpoint_passes_and_evil_one_fails(tmp_path: Path) -> None:
    validate_pretrained_dir(ACT_CHECKPOINT, expected_type="act")
    bad = tmp_path / "pm"
    shutil.copytree(ACT_CHECKPOINT, bad)
    (bad / "policy_preprocessor.json").write_text(json.dumps(EVIL))
    with pytest.raises(UntrustedPretrainedError):
        validate_pretrained_dir(bad)
    with pytest.raises(UntrustedPretrainedError, match="policy type"):
        validate_pretrained_dir(ACT_CHECKPOINT, expected_type="diffusion")


def test_hub_download_is_restricted_to_weights(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import huggingface_hub

    seen: dict[str, Any] = {}
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda repo, **kw: seen.update(repo=repo, **kw))
    init_from._download("attacker/evil", tmp_path / "d", tmp_path / "c", None)
    assert seen["allow_patterns"] == ["config.json", "model.safetensors", "train_config.json"]
    assert seen["repo"] == "attacker/evil" and seen["repo_type"] == "model"


def _sizes(**over: int) -> Any:
    def list_sizes(repo: str, token: str | None) -> dict[str, int]:
        return {"config.json": 10, "model.safetensors": 100, "policy_preprocessor.json": 5, **over}

    return list_sizes


def _evil_download(src: Path) -> Any:
    """A downloader that ignores allow_patterns: the guard must still drop everything else."""

    def download(repo: str, dest: Path, cache: Path, token: str | None) -> None:
        shutil.copyfile(src / "config.json", dest / "config.json")
        shutil.copyfile(src / "model.safetensors", dest / "model.safetensors")
        (dest / "policy_preprocessor.json").write_text(json.dumps(EVIL))
        (dest / "policy_postprocessor.json").write_text(json.dumps(EVIL))
        (dest / "evil.py").write_text("import os; os.system('id')")
        (dest / ".cache" / "huggingface").mkdir(parents=True)

    return download


@requires_act
@requires_golden
def test_fetch_hf_init_builds_trusted_processors(tmp_path: Path) -> None:
    dest = tmp_path / "init" / "pretrained_model"
    out = fetch_hf_init(
        "attacker/evil",
        dest,
        policy_type="act",
        dataset_root=GOLDEN_DATASET,
        dataset_repo_id=GOLDEN_REPO_ID,
        cache_dir=tmp_path / "hub",
        env=child_env(overrides={"HF_HUB_OFFLINE": "1"}),
        max_bytes=10**12,
        list_sizes=_sizes(),
        download=_evil_download(ACT_CHECKPOINT),
    )
    names = sorted(p.name for p in out.iterdir())
    assert "evil.py" not in names and ".cache" not in names
    assert {
        "config.json",
        "model.safetensors",
        "policy_preprocessor.json",
        "policy_postprocessor.json",
    } <= set(names)
    for f in ("policy_preprocessor.json", "policy_postprocessor.json"):
        doc = json.loads((out / f).read_text())
        assert all("class" not in s for s in doc["steps"]) and doc != EVIL
    validate_pretrained_dir(out, expected_type="act")
    # LeRobot really loads the generated processors (fresh interpreter, as lerobot-train would)
    code = (
        "import sys; from lerobot.processor import PolicyProcessorPipeline as P; "
        "P.from_pretrained(sys.argv[1], config_filename='policy_preprocessor.json'); print('ok')"
    )
    r = subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, "-I", "-c", code, str(out)],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert r.stdout.strip().endswith("ok"), r.stderr[-2000:]
    assert not (tmp_path / "PWNED").exists()


def test_fetch_hf_init_rejects_bad_repos(tmp_path: Path) -> None:
    kw: dict[str, Any] = {
        "policy_type": "act",
        "dataset_root": tmp_path,
        "dataset_repo_id": "local/x",
        "cache_dir": tmp_path / "hub",
        "env": {},
        "max_bytes": 1000,
    }
    with pytest.raises(InitFromError) as e:
        fetch_hf_init("a/b", tmp_path / "d1", list_sizes=lambda r, t: {"config.json": 1}, **kw)
    assert e.value.code == "config_invalid" and "model.safetensors" in str(e.value)
    with pytest.raises(InitFromError) as e:
        fetch_hf_init("a/b", tmp_path / "d2", list_sizes=_sizes(**{"model.safetensors": 10**9}), **kw)
    assert e.value.code == "config_invalid" and "limit" in str(e.value)

    def wrong_type(repo: str, dest: Path, cache: Path, token: str | None) -> None:
        (dest / "config.json").write_text(json.dumps({"type": "diffusion"}))
        (dest / "model.safetensors").write_bytes(b"\0")

    with pytest.raises(InitFromError) as e:
        fetch_hf_init("a/b", tmp_path / "d3", list_sizes=_sizes(), download=wrong_type, **kw)
    assert e.value.code == "config_invalid" and "policy type" in str(e.value)

    def boom(*a: Any) -> dict[str, int]:
        raise OSError("network down")

    with pytest.raises(InitFromError) as e:
        fetch_hf_init("a/b", tmp_path / "d4", list_sizes=boom, **kw)
    assert e.value.code == "checkpoint_corrupt"
    assert HF_ALLOW_PATTERNS == ["config.json", "model.safetensors", "train_config.json"]


def test_build_bundle_validates_before_any_lerobot_load(
    small_act: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase-5 N4: the auto-export loaded the child-written processor JSON (load_policy_cpu,
    load_processors, evaluate_heldout) before ``verify`` ran the guard. ``build_bundle`` now
    rejects the checkpoint first; nothing from LeRobot is called and the payload never runs."""
    import uuid

    import export.onnx_export
    import export.samples
    from export.bundle import build_bundle
    from export.types import BundleRequest, DatasetInfo, ExportOptions, RunInfo, TrainingInfo

    bad = tmp_path / "ckpt" / "pretrained_model"
    shutil.copytree(small_act, bad)
    pwned = tmp_path / "PWNED"
    evil = {
        "name": "policy_preprocessor",
        "steps": [{"class": "subprocess.Popen", "config": {"args": ["sh", "-c", f"id > {pwned}"]}}],
    }
    (bad / "policy_preprocessor.json").write_text(json.dumps(evil))
    called: list[str] = []

    def _trap(name: str) -> Any:
        def f(*a: Any, **k: Any) -> Any:
            called.append(name)
            raise AssertionError(f"{name} ran before the guard")

        return f

    monkeypatch.setattr(export.onnx_export, "load_policy_cpu", _trap("load_policy_cpu"))
    monkeypatch.setattr(export.samples, "load_processors", _trap("load_processors"))

    def u() -> str:
        return str(uuid.uuid4())

    req = BundleRequest(
        model_id=u(),
        run=RunInfo(id=u(), number=1, name="r", workspace_id=u()),
        dataset=DatasetInfo(
            dataset_id=u(),
            version_id=u(),
            version=1,
            name="d",
            content_hash="0" * 64,
            repo_id="local/d",
            root=tmp_path / "no-dataset",
        ),
        training=TrainingInfo(
            seed=1,
            total_steps=1,
            batch_size=1,
            mixed_precision="no",
            gpu_name="x",
            heldout_episodes=[0],
            train_episodes=[1],
            gpu_seconds=0.0,
        ),
        pretrained_dir=bad,
        checkpoint_step=1,
        work_dir=tmp_path / "work",
        options=ExportOptions(onnx=True, eval=True),
    )
    with pytest.raises(UntrustedPretrainedError, match="'class'"):
        build_bundle(req)
    assert called == [] and not pwned.exists()
    assert not (tmp_path / "work").exists()  # nothing was even copied
