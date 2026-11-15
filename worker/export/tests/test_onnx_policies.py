"""ONNX export + parity + infer_onnx.py vs LeRobot, on real LeRobot checkpoints (small, random-init)
built against the golden dataset. CPU only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch

from export.bundle import dataset_meta, run_onnx_stage
from export.onnx_export import (
    StaticCenterCrop,
    build_graph_modules,
    inverse_cdf_sample,
    load_policy_cpu,
    vqbet_inverse_cdf,
)
from export.policy_info import load_policy_info
from export.samples import load_processors, obs_from_item, open_dataset
from export.templates.infer_onnx import Array, OnnxPolicy
from export.tests.checkpoints import GOLDEN_DATASET, GOLDEN_REPO_ID
from export.tests.conftest import requires_golden, validate

pytestmark = requires_golden

HELDOUT = [19]


def _stage(
    ckpt: Path, out: Path, *, fp16: bool = False, n: int = 4
) -> tuple[str, str | None, dict[str, Any] | None]:
    info = load_policy_info(ckpt)
    policy = load_policy_cpu(ckpt, info.policy_type)
    meta = dataset_meta(GOLDEN_DATASET, GOLDEN_REPO_ID)
    return run_onnx_stage(
        pretrained_dir=ckpt,
        policy=policy,
        info=info,
        meta=meta,
        onnx_dir=out,
        dataset_root=GOLDEN_DATASET,
        repo_id=GOLDEN_REPO_ID,
        heldout_episodes=HELDOUT,
        fp16=fp16,
        n_samples=n,
    )


def _check_docs(onnx_dir: Path) -> dict[str, Any]:
    io_spec: dict[str, Any] = json.loads((onnx_dir / "io_spec.json").read_text())
    validate(io_spec, "io_spec.schema.json")
    validate(json.loads((onnx_dir / "normalization.json").read_text()), "normalization.schema.json")
    validate(json.loads((onnx_dir / "parity_report.json").read_text()), "parity_report.schema.json")
    assert (onnx_dir / "infer_onnx.py").is_file()
    assert "onnxruntime==" in (onnx_dir / "requirements.txt").read_text()
    return io_spec


def _raw_obs(item: dict[str, Any]) -> dict[str, Array]:
    """Dataset item -> what a robot loop hands infer_onnx.py (uint8 HWC RGB, float32 state)."""
    obs: dict[str, Array] = {}
    for k, v in item.items():
        if k.startswith("observation.images."):
            obs[k] = (v.permute(1, 2, 0).numpy() * 255.0).round().astype(np.uint8)
        elif k == "observation.state":
            obs[k] = v.numpy().astype(np.float32)
    return obs


def _uint8_roundtrip(item: dict[str, Any]) -> dict[str, Any]:
    out = dict(item)
    for k, v in item.items():
        if k.startswith("observation.images."):
            out[k] = (v * 255.0).round() / 255.0
    return out


# ------------------------------------------------------------------------------------------ ACT
def test_act_export_parity_and_fp16(small_act: Path, tmp_path: Path) -> None:
    status, detail, report = _stage(small_act, tmp_path / "onnx", fp16=True)
    assert status == "passed", detail
    assert report is not None and report["passed"]
    comps = {g["comparison"]: g for g in report["graphs"]}
    assert set(comps) == {"model", "model_fp16"}
    assert comps["model"]["max_abs_diff"] < 1e-4 and comps["model"]["gating"]
    assert not comps["model_fp16"]["gating"]
    io = _check_docs(tmp_path / "onnx")
    g = io["graphs"][0]
    assert g["file"] == "model.onnx" and g["fp16_file"] == "model.fp16.onnx"
    assert [t["name"] for t in g["inputs"]] == ["observation.state", "observation.images.wrist_cam"]
    assert g["outputs"][0]["shape"] == ["batch", 10, 6]
    assert io["cameras"][0]["source_codec"] == "av1"
    assert io["action"]["names"][0] == "shoulder_pan.pos"


def test_act_infer_onnx_matches_lerobot_select_action(small_act: Path, tmp_path: Path) -> None:
    """Raw-observation API of infer_onnx.py == LeRobot pre-processor -> select_action -> post-processor,
    frame by frame including the action-chunk queue (chunk 10, n_action_steps 5)."""
    status, detail, _ = _stage(small_act, tmp_path / "onnx")
    assert status == "passed", detail
    onnx_policy = OnnxPolicy(tmp_path)
    policy = load_policy_cpu(small_act, "act")
    pre, post = load_processors(small_act)
    ds = open_dataset(GOLDEN_DATASET, GOLDEN_REPO_ID, HELDOUT)
    policy.reset()
    onnx_policy.reset()
    for i in range(12):
        item = _uint8_roundtrip(ds[i])
        with torch.inference_mode():
            ref = post(policy.select_action(pre(obs_from_item(item)))).reshape(-1).numpy()
        got = onnx_policy.select_action(_raw_obs(item))
        np.testing.assert_allclose(got, ref, atol=2e-3, rtol=1e-4)
    assert len(onnx_policy._action_queue) == 3  # 12 calls = 2 full chunks of 5 + 2 taken


def test_act_temporal_ensemble_matches_lerobot_select_action(tmp_path: Path) -> None:
    """QC-ml-2: with temporal_ensemble_coeff set, LeRobot ACT runs the model every step and blends
    the overlapping chunks. io_spec carries the coefficient and infer_onnx.py reproduces the blend,
    so ONNX rollouts match LeRobot step by step (before: 0.4-0.7 joint units off from step 3)."""
    from export.tests.checkpoints import make_random_checkpoint

    ckpt = make_random_checkpoint(
        "act", tmp_path / "te" / "pretrained_model", temporal_ensemble_coeff=0.01, n_action_steps=1
    )
    status, detail, _ = _stage(ckpt, tmp_path / "onnx")
    assert status == "passed", detail
    io = _check_docs(tmp_path / "onnx")
    assert io["action"]["temporal_ensemble_coeff"] == pytest.approx(0.01)
    onnx_policy = OnnxPolicy(tmp_path)
    assert onnx_policy.ensembler is not None
    policy = load_policy_cpu(ckpt, "act")
    pre, post = load_processors(ckpt)
    ds = open_dataset(GOLDEN_DATASET, GOLDEN_REPO_ID, HELDOUT)
    policy.reset()
    onnx_policy.reset()
    for i in range(15):
        item = _uint8_roundtrip(ds[i])
        with torch.inference_mode():
            ref = post(policy.select_action(pre(obs_from_item(item)))).reshape(-1).numpy()
        got = onnx_policy.select_action(_raw_obs(item))
        np.testing.assert_allclose(got, ref, atol=2e-3, rtol=1e-4, err_msg=f"step {i}")
    # reset() starts a fresh ensemble, as LeRobot does at an episode start
    onnx_policy.reset()
    assert onnx_policy.ensembler.actions is None


def test_act_without_temporal_ensemble_declares_null(small_act: Path, tmp_path: Path) -> None:
    status, _, _ = _stage(small_act, tmp_path / "onnx")
    assert status == "passed"
    io = _check_docs(tmp_path / "onnx")
    assert io["action"]["temporal_ensemble_coeff"] is None
    assert OnnxPolicy(tmp_path).ensembler is None


def test_act_fp16_policy_runs(small_act: Path, tmp_path: Path) -> None:
    status, _, _ = _stage(small_act, tmp_path / "onnx", fp16=True)
    assert status == "passed"
    p = OnnxPolicy(tmp_path / "onnx", fp16=True, rng=np.random.default_rng(0))
    ds = open_dataset(GOLDEN_DATASET, GOLDEN_REPO_ID, HELDOUT)
    a = p.select_action(_raw_obs(ds[0]))
    assert a.shape == (6,) and np.all(np.isfinite(a))
    with pytest.raises(FileNotFoundError):
        OnnxPolicy(tmp_path / "missing")
    (tmp_path / "onnx" / "model.fp16.onnx").unlink()
    spec = json.loads((tmp_path / "onnx" / "io_spec.json").read_text())
    spec["graphs"][0]["fp16_file"] = None
    (tmp_path / "onnx" / "io_spec.json").write_text(json.dumps(spec))
    with pytest.raises(FileNotFoundError, match="fp16"):
        OnnxPolicy(tmp_path / "onnx", fp16=True)


# ------------------------------------------------------------------------------------ diffusion
def test_diffusion_split_export_parity(small_diffusion: Path, tmp_path: Path) -> None:
    status, detail, report = _stage(small_diffusion, tmp_path / "onnx", fp16=True)
    assert status == "passed", detail
    assert report is not None
    comps = {g["comparison"]: g for g in report["graphs"]}
    assert set(comps) == {"obs_encoder", "denoiser_single_step", "full_denoise_loop"}
    assert all(g["gating"] and g["passed"] for g in comps.values())
    io = _check_docs(tmp_path / "onnx")
    assert io["onnx_support"] == "split"
    assert [g["id"] for g in io["graphs"]] == ["obs_encoder", "denoiser"]
    assert all(g["fp16_file"] is None for g in io["graphs"])  # fp16 only for full graphs
    assert io["diffusion"]["scheduler"] == "DDPM" and io["diffusion"]["num_inference_steps"] == 10
    assert io["graphs"][0]["inputs"][1]["shape"] == ["batch", 2, 3, 360, 640]
    assert "stack_obs_steps" in io["image_preprocess"]["steps"]


def test_diffusion_ddim_infer_onnx_matches_lerobot(small_diffusion_ddim: Path, tmp_path: Path) -> None:
    """DDIM is deterministic given the initial noise: the numpy loop in infer_onnx.py must reproduce
    LeRobot's DiffusionPolicy.select_action (observation history + action queue) frame by frame."""
    status, detail, report = _stage(small_diffusion_ddim, tmp_path / "onnx")
    assert status == "passed", detail
    assert report is not None
    policy = load_policy_cpu(small_diffusion_ddim, "diffusion")
    pre, post = load_processors(small_diffusion_ddim)
    onnx_policy = OnnxPolicy(tmp_path / "onnx")
    noise = np.random.default_rng(3).standard_normal((1, 16, 6), dtype=np.float32)
    onnx_policy.noise_fn = lambda shape: noise
    ds = open_dataset(GOLDEN_DATASET, GOLDEN_REPO_ID, HELDOUT)
    policy.reset()
    onnx_policy.reset()
    for i in range(10):
        item = _uint8_roundtrip(ds[i])
        with torch.inference_mode():
            ref = post(policy.select_action(pre(obs_from_item(item)), noise=torch.from_numpy(noise)))
        got = onnx_policy.select_action(_raw_obs(item))
        np.testing.assert_allclose(got, ref.reshape(-1).numpy(), atol=2e-3, rtol=1e-4)


# ---------------------------------------------------------------------------------------- vqbet
def test_vqbet_export_parity(small_vqbet: Path, tmp_path: Path) -> None:
    status, detail, _ = _stage(small_vqbet, tmp_path / "onnx", fp16=True)
    assert status == "passed", detail
    io = _check_docs(tmp_path / "onnx")
    noise = next(t for t in io["graphs"][0]["inputs"] if t["role"] == "sampling_noise")
    assert noise["shape"] == ["batch", 2, 2] and noise["normalized"] is False
    assert io["action"]["chunk_size"] == 4 and io["action"]["n_action_steps"] == 4
    p = OnnxPolicy(tmp_path / "onnx", rng=np.random.default_rng(0))
    ds = open_dataset(GOLDEN_DATASET, GOLDEN_REPO_ID, HELDOUT)
    for i in range(5):
        a = p.select_action(_raw_obs(ds[i]))
        assert a.shape == (6,) and np.all(np.isfinite(a))


def test_vqbet_sampling_noise_drives_codes(small_vqbet: Path) -> None:
    info = load_policy_info(small_vqbet)
    policy = load_policy_cpu(small_vqbet, "vqbet")
    (mod,) = build_graph_modules(policy, info)
    inputs = mod.example_inputs(1)[:-1]
    outs = []
    for u in (0.001, 0.5, 0.999):
        with torch.no_grad():
            outs.append(mod(*inputs, torch.full((1, 2, 2), u)).numpy())
    assert not np.allclose(outs[0], outs[2])
    with torch.no_grad():
        again = mod(*inputs, torch.full((1, 2, 2), 0.5)).numpy()
    np.testing.assert_array_equal(outs[1], again)  # deterministic given u


def test_inverse_cdf_sample() -> None:
    probs = torch.tensor([[0.1, 0.2, 0.7], [0.5, 0.5, 0.0], [0.0, 0.0, 1.0]])
    u = torch.tensor([0.05, 0.75, 0.3])
    assert inverse_cdf_sample(probs, u).reshape(-1).tolist() == [0, 1, 2]
    # rounding: u above the float cumsum still maps to the last bin
    assert inverse_cdf_sample(torch.tensor([[0.3, 0.3, 0.3]]), torch.tensor([0.95])).item() == 2
    # empirical distribution matches probs
    u = torch.rand(20000, generator=torch.Generator().manual_seed(0))
    codes = inverse_cdf_sample(probs[:1].expand(20000, 3), u).reshape(-1)
    freq = torch.bincount(codes, minlength=3).float() / 20000
    assert torch.allclose(freq, probs[0], atol=0.02)


def test_vqbet_patch_is_restored(small_vqbet: Path) -> None:
    from lerobot.policies.vqbet import modeling_vqbet as mv

    real = mv.torch
    with vqbet_inverse_cdf(torch.zeros(1, 1, 2), sequential=False):
        assert mv.torch is not real
        assert mv.torch.cat is torch.cat
        with pytest.raises(ValueError):
            mv.torch.multinomial(torch.ones(1, 2), num_samples=2)
    assert mv.torch is real


# ------------------------------------------------------------------------------------------ misc
@pytest.mark.parametrize(
    ("in_hw", "crop"), [((360, 640), (84, 84)), ((97, 101), (40, 33)), ((10, 10), (10, 10))]
)
def test_static_center_crop_matches_torchvision(in_hw: tuple[int, int], crop: tuple[int, int]) -> None:
    import torchvision

    x = torch.randn(2, 3, *in_hw)
    np.testing.assert_array_equal(
        StaticCenterCrop(in_hw, crop)(x).numpy(), torchvision.transforms.CenterCrop(crop)(x).numpy()
    )
    with pytest.raises(ValueError):
        StaticCenterCrop((10, 10), (11, 10))


def test_unsupported_policy_types_raise(small_act: Path) -> None:
    import dataclasses

    info = load_policy_info(small_act)
    fake = dataclasses.replace(info, policy_type="smolvla")
    assert fake.onnx_support == "none"
    with pytest.raises(ValueError, match="no ONNX"):
        build_graph_modules(load_policy_cpu(small_act, "act"), fake)


def test_export_failure_removes_onnx_dir(small_act: Path, tmp_path: Path) -> None:
    import dataclasses

    info = load_policy_info(small_act)
    policy = load_policy_cpu(small_act, "act")
    meta = dataset_meta(GOLDEN_DATASET, GOLDEN_REPO_ID)
    bad = dataclasses.replace(info, policy_type="tdmpc")
    status, detail, report = run_onnx_stage(
        pretrained_dir=small_act,
        policy=policy,
        info=bad,
        meta=meta,
        onnx_dir=tmp_path / "onnx",
        dataset_root=GOLDEN_DATASET,
        repo_id=GOLDEN_REPO_ID,
        heldout_episodes=HELDOUT,
    )
    assert status == "failed" and report is None and detail and detail.startswith("export:")
    assert not (tmp_path / "onnx").exists()


def test_parity_miss_is_reported_not_raised(
    small_act: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corrupt the torch reference: parity must fail with passed=false and keep onnx/ for inspection."""
    from export import parity

    real_add = parity._Acc.add

    def skewed(self: Any, onnx_out: Array, torch_out: Array, unnorm: Any) -> None:
        real_add(self, onnx_out + 1e-2, torch_out, unnorm)

    monkeypatch.setattr(parity._Acc, "add", skewed)
    status, detail, report = _stage(small_act, tmp_path / "onnx")
    assert status == "failed" and detail == "parity above threshold: model"
    assert report is not None and not report["passed"]
    validate(report, "parity_report.schema.json")
    assert (tmp_path / "onnx" / "parity_report.json").is_file()
