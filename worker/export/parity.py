"""ONNX vs PyTorch parity (docs/spec/bundle.md §6) -> ``onnx/parity_report.json``."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import Tensor

from export.onnx_export import ExportedOnnx, GraphModule, GraphSpec
from export.policy_info import PolicyInfo
from export.samples import ParitySamples
from export.templates.infer_onnx import Array, NoiseScheduler, denormalize

THRESHOLDS: dict[str, tuple[float, float, bool]] = {
    # comparison: (atol, rtol, gating)
    "model": (1e-4, 1e-4, True),
    "obs_encoder": (1e-4, 1e-4, True),
    "denoiser_single_step": (1e-4, 1e-4, True),
    "full_denoise_loop": (1e-3, 1e-3, True),
    "model_fp16": (1e-2, 1e-2, False),
}


@dataclass
class _Acc:
    comparison: str
    file: str
    atol: float
    rtol: float
    gating: bool
    max_abs: float = 0.0
    max_rel: float = 0.0
    sum_abs: float = 0.0
    count: int = 0
    max_abs_unnorm: float | None = None
    passed: bool = True
    _unnorm: list[float] = field(default_factory=list)

    def add(self, onnx_out: Array, torch_out: Array, unnorm: tuple[Array, Array] | None) -> None:
        a = onnx_out.astype(np.float64)
        b = torch_out.astype(np.float64)
        if a.shape != b.shape:
            raise ValueError(f"{self.comparison}: shape mismatch onnx {a.shape} vs torch {b.shape}")
        diff = np.abs(a - b)
        self.max_abs = max(self.max_abs, float(diff.max(initial=0.0)))
        # relative error, bounded near zero by atol (same scale as the allclose criterion)
        self.max_rel = max(self.max_rel, float((diff / (np.abs(b) + self.atol)).max(initial=0.0)))
        self.sum_abs += float(diff.sum())
        self.count += int(diff.size)
        self.passed = self.passed and bool(np.allclose(a, b, atol=self.atol, rtol=self.rtol))
        if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
            self.passed = False
        if unnorm is not None:
            ua, ub = unnorm
            self._unnorm.append(float(np.abs(ua.astype(np.float64) - ub.astype(np.float64)).max(initial=0.0)))

    def to_json(self) -> dict[str, Any]:
        return {
            "comparison": self.comparison,
            "file": self.file,
            "atol": self.atol,
            "rtol": self.rtol,
            "max_abs_diff": self.max_abs,
            "max_rel_diff": self.max_rel,
            "mean_abs_diff": self.sum_abs / max(self.count, 1),
            "max_abs_diff_unnormalized": max(self._unnorm) if self._unnorm else None,
            "passed": self.passed and self.count > 0,
            "gating": self.gating,
        }


def _acc(comparison: str, file: str) -> _Acc:
    atol, rtol, gating = THRESHOLDS[comparison]
    return _Acc(comparison=comparison, file=file, atol=atol, rtol=rtol, gating=gating)


def _session(path: Path) -> Any:
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    return ort.InferenceSession(str(path), sess_options=opts, providers=["CPUExecutionProvider"])


def _graph_inputs(module: GraphModule, batch: dict[str, Tensor], extra: dict[str, Tensor]) -> list[Tensor]:
    out: list[Tensor] = []
    for spec in module.input_specs:
        if spec.lerobot_key is not None and spec.lerobot_key in batch:
            out.append(batch[spec.lerobot_key])
        elif spec.name in extra:
            out.append(extra[spec.name])
        else:
            raise KeyError(f"no value for graph input {spec.name}")
    return out


def _run_onnx(sess: Any, specs: list[Any], tensors: list[Tensor]) -> Array:
    feeds = {s.name: t.detach().cpu().numpy() for s, t in zip(specs, tensors, strict=True)}
    return np.asarray(sess.run(None, feeds)[0])


def _unnorm_action(x: Array, normalization: dict[str, Any]) -> Array:
    feat = normalization["features"].get("action")
    return denormalize(x, feat, float(normalization["eps"])) if feat else x


@contextlib.contextmanager
def _ddpm_noise_from(queue: list[Array]) -> Iterator[None]:
    """Feed diffusers' DDPM variance noise from ``queue`` (same draws as the numpy loop)."""
    from diffusers.schedulers import scheduling_ddpm

    # scheduling_ddpm.step() looks ``randn_tensor`` up in its module globals at call time.
    namespace: dict[str, Any] = vars(scheduling_ddpm)
    real = namespace["randn_tensor"]

    def fake(shape: Any, generator: Any = None, device: Any = None, dtype: Any = None, **_: Any) -> Tensor:
        arr = queue.pop(0)
        if tuple(arr.shape) != tuple(shape):
            raise ValueError(f"noise shape {arr.shape} != requested {tuple(shape)}")
        return torch.from_numpy(arr).to(dtype=dtype or torch.float32)

    namespace["randn_tensor"] = fake
    try:
        yield
    finally:
        namespace["randn_tensor"] = real


def _numpy_denoise(
    scheduler: NoiseScheduler,
    denoiser: Any,
    global_cond: Array,
    horizon: int,
    action_dim: int,
    rng: np.random.Generator,
) -> tuple[Array, list[Array]]:
    """The infer_onnx.py loop with recorded noise draws."""
    drawn: list[Array] = []

    def draw(shape: tuple[int, ...]) -> Array:
        arr = rng.standard_normal(shape, dtype=np.float32)
        drawn.append(arr)
        return arr

    b = global_cond.shape[0]
    sample = draw((b, horizon, action_dim))
    for i, t in enumerate(scheduler.timesteps):
        out = denoiser.run(
            None,
            {
                "noisy_action": sample,
                "timestep": np.full((b,), int(t), dtype=np.int64),
                "global_cond": global_cond,
            },
        )[0]
        sample = scheduler.step(np.asarray(out), i, sample, draw)
    return sample, drawn


def run_parity(
    *,
    policy: Any,
    info: PolicyInfo,
    exported: ExportedOnnx,
    onnx_dir: Path,
    samples: ParitySamples,
    normalization: dict[str, Any],
    io_spec: dict[str, Any],
    seed: int = 0,
    full_loop_samples: int | None = None,
) -> dict[str, Any]:
    """Compare every exported graph against its PyTorch wrapper on the same normalised inputs."""
    torch.manual_seed(seed)
    np_rng = np.random.default_rng(seed)
    specs: dict[str, GraphSpec] = {g.id: g for g in exported.graphs}
    accs: list[_Acc] = []

    if info.policy_type in ("act", "vqbet"):
        mod = exported.modules["model"]
        g = specs["model"]
        main = _acc("model", g.file)
        sess = _session(onnx_dir / g.file)
        fp16_acc = _acc("model_fp16", g.fp16_file) if g.fp16_file else None
        sess16 = _session(onnx_dir / g.fp16_file) if g.fp16_file else None
        for batch in samples.batches:
            extra: dict[str, Tensor] = {}
            if info.policy_type == "vqbet":
                shape = [1 if d == "batch" else int(d) for d in mod.input_specs[-1].shape]
                extra["sampling_noise"] = torch.from_numpy(np_rng.random(shape, dtype=np.float32))
            inputs = _graph_inputs(mod, batch, extra)
            with torch.no_grad():
                ref = mod(*inputs).detach().cpu().numpy()
            out = _run_onnx(sess, mod.input_specs, inputs)
            main.add(out, ref, (_unnorm_action(out, normalization), _unnorm_action(ref, normalization)))
            if fp16_acc is not None and sess16 is not None:
                out16 = _run_onnx(sess16, mod.input_specs, inputs)
                fp16_acc.add(
                    out16, ref, (_unnorm_action(out16, normalization), _unnorm_action(ref, normalization))
                )
        accs.append(main)
        if fp16_acc is not None:
            accs.append(fp16_acc)

    elif info.policy_type == "diffusion":
        enc_mod = exported.modules["obs_encoder"]
        den_mod = exported.modules["denoiser"]
        enc_sess = _session(onnx_dir / specs["obs_encoder"].file)
        den_sess = _session(onnx_dir / specs["denoiser"].file)
        enc_acc = _acc("obs_encoder", specs["obs_encoder"].file)
        step_acc = _acc("denoiser_single_step", specs["denoiser"].file)
        loop_acc = _acc("full_denoise_loop", specs["denoiser"].file)
        dspec = io_spec["diffusion"]
        scheduler = NoiseScheduler(dspec)
        horizon = int(dspec["horizon"])
        adim = info.action.shape[0]
        n_steps = int(dspec["num_train_timesteps"])
        loop_n = len(samples.batches) if full_loop_samples is None else full_loop_samples
        loop_rng = np.random.default_rng(seed)
        for i, batch in enumerate(samples.batches):
            inputs = _graph_inputs(enc_mod, batch, {})
            with torch.no_grad():
                gc_ref = enc_mod(*inputs)
            gc_onnx = _run_onnx(enc_sess, enc_mod.input_specs, inputs)
            enc_acc.add(gc_onnx, gc_ref.numpy(), None)
            for _ in range(3):
                t = int(np_rng.integers(0, n_steps))
                noisy = torch.from_numpy(np_rng.standard_normal((1, horizon, adim), dtype=np.float32))
                ts = torch.full((1,), t, dtype=torch.long)
                with torch.no_grad():
                    ref = den_mod(noisy, ts, gc_ref).numpy()
                out = _run_onnx(den_sess, den_mod.input_specs, [noisy, ts, gc_ref])
                step_acc.add(out, ref, None)
            if i < loop_n:
                sample_np, drawn = _numpy_denoise(scheduler, den_sess, gc_onnx, horizon, adim, loop_rng)
                queue = list(drawn[1:])
                with torch.no_grad(), _ddpm_noise_from(queue):
                    sample_ref = policy.diffusion.conditional_sample(
                        1, global_cond=gc_ref, noise=torch.from_numpy(drawn[0])
                    ).numpy()
                if queue:
                    raise RuntimeError(
                        f"torch loop consumed {len(drawn) - 1 - len(queue)} of {len(drawn) - 1} noises"
                    )
                loop_acc.add(
                    sample_np,
                    sample_ref,
                    (_unnorm_action(sample_np, normalization), _unnorm_action(sample_ref, normalization)),
                )
        accs += [enc_acc, step_acc, loop_acc]
    else:
        raise ValueError(f"no parity for policy type {info.policy_type!r}")

    graphs = [a.to_json() for a in accs]
    passed = all(g["passed"] for g in graphs if g["gating"])
    return {
        "schema_version": "1",
        "passed": passed,
        "provider": "CPUExecutionProvider",
        "torch_device": "cpu",
        "n_samples": len(samples.batches),
        "sample_source": samples.source,
        "seed": seed,
        "graphs": graphs,
    }
