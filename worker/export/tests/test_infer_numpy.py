"""infer_onnx.py numpy parts vs the libraries LeRobot uses (diffusers schedulers, lerobot normalizer)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
import torch

from export.templates.infer_onnx import Array, NoiseScheduler, _resolve_onnx_dir, denormalize, normalize

MODES = ["MEAN_STD", "MIN_MAX", "QUANTILES", "QUANTILE10", "IDENTITY"]


def _stats(rng: np.random.Generator, dim: int) -> dict[str, Array]:
    lo = rng.normal(size=dim).astype(np.float32)
    hi = lo + rng.uniform(0.5, 3.0, size=dim).astype(np.float32)
    hi[0] = lo[0]  # degenerate range -> eps branch
    return {
        "mean": rng.normal(size=dim).astype(np.float32),
        "std": rng.uniform(0.1, 2.0, size=dim).astype(np.float32),
        "min": lo,
        "max": hi,
        "q01": lo,
        "q99": hi,
        "q10": lo + 0.1,
        "q90": hi - 0.1,
    }


@pytest.mark.parametrize("mode", MODES)
def test_normalize_matches_lerobot(mode: str) -> None:
    from lerobot.configs.types import FeatureType, NormalizationMode, PolicyFeature
    from lerobot.processor.normalize_processor import NormalizerProcessorStep

    rng = np.random.default_rng(1)
    st = _stats(rng, 6)
    img = {k: v[:3].reshape(3, 1, 1) for k, v in _stats(rng, 3).items()}
    step = NormalizerProcessorStep(
        features={
            "observation.state": PolicyFeature(FeatureType.STATE, (6,)),
            "observation.images.cam": PolicyFeature(FeatureType.VISUAL, (3, 4, 5)),
        },
        norm_map={FeatureType.STATE: NormalizationMode(mode), FeatureType.VISUAL: NormalizationMode(mode)},
        stats={"observation.state": st, "observation.images.cam": img},
    )
    feat_s: dict[str, Any] = {"mode": mode, **{k: v.tolist() for k, v in st.items()}}
    feat_i: dict[str, Any] = {"mode": mode, **{k: v.reshape(-1).tolist() for k, v in img.items()}}
    x = rng.normal(size=(2, 6)).astype(np.float32) * 5
    im = rng.uniform(0, 1, size=(2, 3, 4, 5)).astype(np.float32)
    for inverse in (False, True):
        ref_s = step._apply_transform(
            torch.from_numpy(x), "observation.state", FeatureType.STATE, inverse=inverse
        )
        ref_i = step._apply_transform(
            torch.from_numpy(im), "observation.images.cam", FeatureType.VISUAL, inverse=inverse
        )
        fn = denormalize if inverse else normalize
        np.testing.assert_allclose(fn(x, feat_s, 1e-8), ref_s.numpy(), rtol=1e-6, atol=1e-5)
        np.testing.assert_allclose(fn(im, feat_i, 1e-8, channel_axis=1), ref_i.numpy(), rtol=1e-6, atol=1e-5)
    if mode != "IDENTITY":
        y = normalize(x, feat_s, 1e-8)
        np.testing.assert_allclose(denormalize(y, feat_s, 1e-8)[:, 1:], x[:, 1:], rtol=1e-5, atol=1e-4)


SCHED_CASES = [
    ("DDPM", "squaredcos_cap_v2", "epsilon", True, 100, None),
    ("DDPM", "linear", "sample", False, 50, 10),
    ("DDPM", "scaled_linear", "epsilon", True, 100, 7),
    ("DDPM", "sigmoid", "epsilon", True, 20, None),
    ("DDIM", "squaredcos_cap_v2", "epsilon", True, 100, 10),
    ("DDIM", "linear", "sample", False, 100, 25),
]


@pytest.mark.parametrize(("kind", "schedule", "pred", "clip", "n_train", "n_inf"), SCHED_CASES)
def test_scheduler_matches_diffusers(
    kind: str, schedule: str, pred: str, clip: bool, n_train: int, n_inf: int | None
) -> None:
    from diffusers import DDIMScheduler, DDPMScheduler

    spec = {
        "scheduler": kind,
        "num_train_timesteps": n_train,
        "num_inference_steps": n_inf or n_train,
        "beta_schedule": schedule,
        "beta_start": 1e-4,
        "beta_end": 0.02,
        "prediction_type": pred,
        "clip_sample": clip,
        "clip_sample_range": 1.0,
        "horizon": 8,
    }
    cls: Any = DDPMScheduler if kind == "DDPM" else DDIMScheduler
    ref: Any = cls(
        num_train_timesteps=n_train,
        beta_start=1e-4,
        beta_end=0.02,
        beta_schedule=schedule,
        clip_sample=clip,
        clip_sample_range=1.0,
        prediction_type=pred,
    )
    ref.set_timesteps(n_inf or n_train)
    ours = NoiseScheduler(spec)
    np.testing.assert_array_equal(ours.timesteps, ref.timesteps.numpy())
    np.testing.assert_allclose(ours.alphas_cumprod, ref.alphas_cumprod.numpy(), rtol=1e-6)

    rng = np.random.default_rng(0)
    sample = rng.standard_normal((2, 8, 3), dtype=np.float32)
    ts = sample.copy()
    noises: list[Array] = []

    def draw(shape: tuple[int, ...]) -> Array:
        arr = rng.standard_normal(shape, dtype=np.float32)
        noises.append(arr)
        return arr

    from export.parity import _ddpm_noise_from

    for i, t in enumerate(ours.timesteps):
        model_out = np.tanh(sample * 0.7 + float(t) / n_train).astype(np.float32)
        n_before = len(noises)
        sample = ours.step(model_out, i, sample, draw)
        model_out_t = torch.tanh(torch.from_numpy(ts) * 0.7 + float(t) / n_train)
        queue = list(noises[n_before:])  # the variance noise drawn by this numpy step (DDPM, t > 0)
        with _ddpm_noise_from(queue):
            ts = ref.step(model_out_t, int(t), torch.from_numpy(ts)).prev_sample.numpy()
        assert not queue  # diffusers consumed exactly the draws numpy made
        np.testing.assert_allclose(sample, ts, rtol=1e-4, atol=1e-5)


def test_scheduler_rejects_unknown() -> None:
    base = {
        "num_train_timesteps": 10,
        "num_inference_steps": 10,
        "beta_schedule": "linear",
        "beta_start": 1e-4,
        "beta_end": 0.02,
        "prediction_type": "epsilon",
        "clip_sample": True,
        "clip_sample_range": 1.0,
    }
    with pytest.raises(ValueError):
        NoiseScheduler({**base, "scheduler": "PNDM"})
    with pytest.raises(ValueError):
        NoiseScheduler({**base, "scheduler": "DDPM", "beta_schedule": "cosine_typo"})
    s = NoiseScheduler({**base, "scheduler": "DDPM", "prediction_type": "v_prediction"})
    with pytest.raises(ValueError):
        s.step(np.zeros((1, 2, 2), np.float32), 0, np.zeros((1, 2, 2), np.float32), lambda sh: np.zeros(sh))


def test_resolve_onnx_dir(tmp_path: Any) -> None:
    (tmp_path / "onnx").mkdir()
    (tmp_path / "onnx" / "io_spec.json").write_text("{}")
    assert _resolve_onnx_dir(tmp_path) == (tmp_path / "onnx").resolve()
    assert _resolve_onnx_dir(tmp_path / "onnx") == (tmp_path / "onnx").resolve()
    with pytest.raises(FileNotFoundError):
        _resolve_onnx_dir(tmp_path / "nope")
