#!/usr/bin/env python3
"""Standalone ONNX inference for a Hibiscus model bundle (docs/spec/bundle.md §7).

Needs only ``numpy`` and ``onnxruntime`` (``opencv-python-headless`` optionally, to resize camera
frames whose size differs from the trained resolution). No LeRobot / PyTorch dependency.

Usage as a library::

    from infer_onnx import OnnxPolicy
    policy = OnnxPolicy("path/to/<bundle_name>")
    policy.reset()                                   # at the start of every episode
    action = policy.select_action({
        "observation.state": state_f32,              # [S] raw joint units
        "observation.images.wrist_cam": frame_u8,    # [H, W, 3] RGB uint8
    })                                               # -> [A] raw joint units

Self-test::

    python infer_onnx.py --bundle .. --selftest
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray

cv2: Any
try:  # optional: only used to resize frames that do not match the trained resolution
    cv2 = importlib.import_module("cv2")
except ImportError:  # pragma: no cover - depends on the user's environment
    cv2 = None

Array = NDArray[Any]
NoiseFn = Callable[[tuple[int, ...]], Array]

__all__ = [
    "Array",
    "NoiseScheduler",
    "OnnxPolicy",
    "denormalize",
    "normalize",
]


# --------------------------------------------------------------------------------------------
# Normalisation (identical to lerobot.processor.normalize_processor)
# --------------------------------------------------------------------------------------------
def _f32(x: Any) -> Array:
    out: Array = np.asarray(x, dtype=np.float32)
    return out


def _stats(feat: dict[str, Any], name: str) -> Array:
    return _f32(feat[name])


def _broadcast(stat: Array, x: Array, channel_axis: int | None) -> Array:
    """Images carry per-channel stats ([3]); reshape them to broadcast over [..., C, H, W]."""
    if channel_axis is None:
        return stat
    shape = [1] * x.ndim
    shape[channel_axis] = stat.shape[0]
    return stat.reshape(shape)


def normalize(x: Array, feat: dict[str, Any], eps: float, channel_axis: int | None = None) -> Array:
    """Map raw values into the policy's normalised space."""
    x = x.astype(np.float32, copy=False)
    mode = feat["mode"]
    if mode == "IDENTITY":
        return x
    if mode == "MEAN_STD":
        mean = _broadcast(_stats(feat, "mean"), x, channel_axis)
        std = _broadcast(_stats(feat, "std"), x, channel_axis)
        return _f32((x - mean) / (std + np.float32(eps)))
    lo_name, hi_name = {"MIN_MAX": ("min", "max"), "QUANTILES": ("q01", "q99"), "QUANTILE10": ("q10", "q90")}[
        mode
    ]
    lo = _broadcast(_stats(feat, lo_name), x, channel_axis)
    hi = _broadcast(_stats(feat, hi_name), x, channel_axis)
    denom = hi - lo
    denom = np.where(denom == 0, np.float32(eps), denom).astype(np.float32)
    return _f32(np.float32(2.0) * (x - lo) / denom - np.float32(1.0))


def denormalize(x: Array, feat: dict[str, Any], eps: float, channel_axis: int | None = None) -> Array:
    """Exact inverse of :func:`normalize`."""
    x = x.astype(np.float32, copy=False)
    mode = feat["mode"]
    if mode == "IDENTITY":
        return x
    if mode == "MEAN_STD":
        mean = _broadcast(_stats(feat, "mean"), x, channel_axis)
        std = _broadcast(_stats(feat, "std"), x, channel_axis)
        return _f32(x * (std + np.float32(eps)) + mean)
    lo_name, hi_name = {"MIN_MAX": ("min", "max"), "QUANTILES": ("q01", "q99"), "QUANTILE10": ("q10", "q90")}[
        mode
    ]
    lo = _broadcast(_stats(feat, lo_name), x, channel_axis)
    hi = _broadcast(_stats(feat, hi_name), x, channel_axis)
    denom = hi - lo
    denom = np.where(denom == 0, np.float32(eps), denom).astype(np.float32)
    return _f32((x + np.float32(1.0)) / np.float32(2.0) * denom + lo)


# --------------------------------------------------------------------------------------------
# Diffusion noise schedulers (numpy port of diffusers DDPMScheduler / DDIMScheduler as used by
# LeRobot's DiffusionPolicy: variance_type=fixed_small, timestep_spacing=leading, steps_offset=0,
# DDIM eta=0, set_alpha_to_one=True, no thresholding). float32 arithmetic like the torch version.
# --------------------------------------------------------------------------------------------
def _betas(schedule: str, n: int, beta_start: float, beta_end: float) -> Array:
    if schedule == "linear":
        return np.linspace(beta_start, beta_end, n, dtype=np.float32)
    if schedule == "scaled_linear":
        return (np.linspace(beta_start**0.5, beta_end**0.5, n, dtype=np.float32) ** 2).astype(np.float32)
    if schedule == "squaredcos_cap_v2":
        import math

        def alpha_bar(t: float) -> float:
            return math.cos((t + 0.008) / 1.008 * math.pi / 2) ** 2

        betas = [min(1 - alpha_bar((i + 1) / n) / alpha_bar(i / n), 0.999) for i in range(n)]
        return np.asarray(betas, dtype=np.float32)
    if schedule == "sigmoid":
        x = np.linspace(-6, 6, n, dtype=np.float32)
        return (1.0 / (1.0 + np.exp(-x)) * (beta_end - beta_start) + beta_start).astype(np.float32)
    raise ValueError(f"unsupported beta_schedule {schedule!r}")


class NoiseScheduler:
    """DDPM / DDIM stepping exactly like ``diffusers`` (float32)."""

    def __init__(self, spec: dict[str, Any]) -> None:
        self.kind: str = spec["scheduler"]
        if self.kind not in ("DDPM", "DDIM"):
            raise ValueError(f"unsupported scheduler {self.kind!r}")
        self.num_train_timesteps = int(spec["num_train_timesteps"])
        self.num_inference_steps = int(spec["num_inference_steps"])
        self.prediction_type: str = spec["prediction_type"]
        self.clip_sample = bool(spec["clip_sample"])
        self.clip_sample_range = np.float32(spec["clip_sample_range"])
        self.betas = _betas(
            spec["beta_schedule"], self.num_train_timesteps, spec["beta_start"], spec["beta_end"]
        )
        self.alphas = (np.float32(1.0) - self.betas).astype(np.float32)
        self.alphas_cumprod = np.cumprod(self.alphas, dtype=np.float32)
        step_ratio = self.num_train_timesteps // self.num_inference_steps
        self.timesteps = (np.arange(0, self.num_inference_steps) * step_ratio).round()[::-1].astype(np.int64)

    def _prev_timestep(self, index: int) -> int:
        if self.kind == "DDIM":
            return int(self.timesteps[index]) - self.num_train_timesteps // self.num_inference_steps
        return int(self.timesteps[index + 1]) if index + 1 < len(self.timesteps) else -1

    def _x0(self, model_output: Array, sample: Array, alpha_prod_t: np.float32) -> Array:
        beta_prod_t = np.float32(1.0) - alpha_prod_t
        if self.prediction_type == "epsilon":
            x0 = (sample - np.sqrt(beta_prod_t) * model_output) / np.sqrt(alpha_prod_t)
        elif self.prediction_type == "sample":
            x0 = model_output
        else:
            raise ValueError(f"unsupported prediction_type {self.prediction_type!r}")
        if self.clip_sample:
            x0 = np.clip(x0, -self.clip_sample_range, self.clip_sample_range)
        return _f32(x0)

    def step(self, model_output: Array, index: int, sample: Array, noise_fn: NoiseFn) -> Array:
        t = int(self.timesteps[index])
        prev_t = self._prev_timestep(index)
        one = np.float32(1.0)
        alpha_prod_t = self.alphas_cumprod[t]
        alpha_prod_t_prev = self.alphas_cumprod[prev_t] if prev_t >= 0 else one
        x0 = self._x0(model_output, sample, alpha_prod_t)
        beta_prod_t = one - alpha_prod_t
        if self.kind == "DDIM":
            if self.prediction_type == "epsilon":
                eps = model_output
            else:
                eps = (sample - np.sqrt(alpha_prod_t) * x0) / np.sqrt(beta_prod_t)
            direction = np.sqrt(one - alpha_prod_t_prev) * eps
            return _f32(np.sqrt(alpha_prod_t_prev) * x0 + direction)
        beta_prod_t_prev = one - alpha_prod_t_prev
        current_alpha_t = alpha_prod_t / alpha_prod_t_prev
        current_beta_t = one - current_alpha_t
        x0_coeff = (np.sqrt(alpha_prod_t_prev) * current_beta_t) / beta_prod_t
        cur_coeff = np.sqrt(current_alpha_t) * beta_prod_t_prev / beta_prod_t
        prev = x0_coeff * x0 + cur_coeff * sample
        if t > 0:
            variance = np.maximum(beta_prod_t_prev / beta_prod_t * current_beta_t, np.float32(1e-20))
            prev = prev + np.sqrt(variance) * noise_fn(model_output.shape).astype(np.float32)
        return np.asarray(prev, dtype=np.float32)


# --------------------------------------------------------------------------------------------
# ACT temporal ensembling (lerobot.policies.act.modeling_act.ACTTemporalEnsembler)
# --------------------------------------------------------------------------------------------
class TemporalEnsembler:
    """Online weighted average of overlapping ACT chunks, w_i = exp(-coeff * i), w_0 = oldest.

    Same algorithm and update order as LeRobot's ``ACTTemporalEnsembler``: every step the new
    chunk ``[B, chunk, A]`` is blended into the running ensemble and its first action is popped.
    """

    def __init__(self, coeff: float, chunk_size: int) -> None:
        self.chunk_size = int(chunk_size)
        self.weights = np.exp(-float(coeff) * np.arange(self.chunk_size, dtype=np.float32)).astype(np.float32)
        self.weights_cumsum = np.cumsum(self.weights).astype(np.float32)
        self.reset()

    def reset(self) -> None:
        self.actions: Array | None = None
        self.counts: Array | None = None  # [n, 1] int64: how many chunks went into each step

    def update(self, actions: Array) -> Array:
        actions = np.asarray(actions, dtype=np.float32)
        if self.actions is None or self.counts is None:
            self.actions = actions.copy()
            self.counts = np.ones((self.chunk_size, 1), dtype=np.int64)
        else:
            c = self.counts
            ens = self.actions * self.weights_cumsum[c - 1]
            ens = ens + actions[:, :-1] * self.weights[c]
            ens = ens / self.weights_cumsum[c]
            c = np.minimum(c + 1, self.chunk_size)
            self.actions = np.concatenate([ens, actions[:, -1:]], axis=1).astype(np.float32)
            self.counts = np.concatenate([c, np.ones_like(c[-1:])], axis=0)
        action, self.actions, self.counts = self.actions[:, 0], self.actions[:, 1:], self.counts[1:]
        return action


# --------------------------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------------------------
def _resolve_onnx_dir(bundle_dir: str | Path) -> Path:
    p = Path(bundle_dir).resolve()
    if (p / "io_spec.json").is_file():
        return p
    if (p / "onnx" / "io_spec.json").is_file():
        return p / "onnx"
    raise FileNotFoundError(f"no io_spec.json under {p} or {p / 'onnx'}")


class OnnxPolicy:
    """Runs a bundle's ONNX graph(s) with LeRobot-equivalent pre/post-processing and queues."""

    def __init__(
        self,
        bundle_dir: str | Path,
        *,
        providers: Sequence[str] | None = None,
        fp16: bool = False,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.onnx_dir = _resolve_onnx_dir(bundle_dir)
        self.io_spec: dict[str, Any] = json.loads((self.onnx_dir / "io_spec.json").read_text())
        norm = json.loads((self.onnx_dir / self.io_spec["normalization_file"]).read_text())
        self.eps = float(norm["eps"])
        self.norm_features: dict[str, dict[str, Any]] = norm["features"]
        self.policy_type: str = self.io_spec["policy_type"]
        self.n_obs_steps = int(self.io_spec.get("n_obs_steps", 1))
        self.chunk_size = int(self.io_spec["action"]["chunk_size"])
        self.n_action_steps = int(self.io_spec["action"]["n_action_steps"])
        self.action_dim = int(self.io_spec["action"]["dim"])
        self.rng = rng if rng is not None else np.random.default_rng()
        #: Optional override of the diffusion noise source (deterministic replays / tests).
        self.noise_fn: NoiseFn | None = None
        provs = list(providers) if providers else ["CPUExecutionProvider"]
        self.sessions: dict[str, Any] = {}
        self.graphs: dict[str, dict[str, Any]] = {}
        for g in self.io_spec["graphs"]:
            fname = g["file"]
            if fp16:
                if not g.get("fp16_file"):
                    raise FileNotFoundError(f"graph {g['id']} has no fp16 variant")
                fname = g["fp16_file"]
            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            self.sessions[g["id"]] = ort.InferenceSession(
                str(self.onnx_dir / fname), sess_options=opts, providers=provs
            )
            self.graphs[g["id"]] = g
        self.scheduler = NoiseScheduler(self.io_spec["diffusion"]) if self.io_spec.get("diffusion") else None
        coeff = self.io_spec["action"].get("temporal_ensemble_coeff")
        #: ACT with ``temporal_ensemble_coeff``: run the graph every step and blend chunks.
        self.ensembler = (
            TemporalEnsembler(float(coeff), self.chunk_size)
            if coeff is not None and self.policy_type == "act"
            else None
        )
        self.reset()

    # ---- state ---------------------------------------------------------------------------
    def reset(self) -> None:
        """Clear observation history and the action queue (call at every episode start)."""
        self._obs_queue: dict[str, deque[Array]] = {}
        self._action_queue: deque[Array] = deque()
        if getattr(self, "ensembler", None) is not None:
            self.ensembler.reset()  # type: ignore[union-attr]

    # ---- preprocessing -------------------------------------------------------------------
    def preprocess_image(self, key: str, frame: Array) -> Array:
        """uint8 HWC RGB -> float32 [3, H, W] normalised (io_spec.image_preprocess.steps)."""
        cam = next(c for c in self.io_spec["cameras"] if c["key"] == key)
        h, w = int(cam["height"]), int(cam["width"])
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError(f"{key}: expected HWC RGB frame, got shape {frame.shape}")
        if frame.shape[0] != h or frame.shape[1] != w:
            if cv2 is None:
                raise ValueError(
                    f"{key}: frame {frame.shape[:2]} != trained ({h}, {w}); install opencv to resize"
                )
            frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
        x = frame.astype(np.float32) / np.float32(255.0)
        x = np.ascontiguousarray(x.transpose(2, 0, 1))
        feat = self.norm_features.get(key)
        return normalize(x, feat, self.eps, channel_axis=0) if feat else x

    def preprocess(self, obs: dict[str, Array]) -> dict[str, Array]:
        """Raw observation dict -> normalised per-key arrays without batch dim."""
        out: dict[str, Array] = {}
        for cam in self.io_spec["cameras"]:
            out[cam["key"]] = self.preprocess_image(cam["key"], np.asarray(obs[cam["key"]]))
        for key in ("observation.state", "observation.environment_state"):
            if self._has_input(key):
                x = np.asarray(obs[key], dtype=np.float32)
                feat = self.norm_features.get(key)
                out[key] = normalize(x, feat, self.eps) if feat else x
        return out

    def _has_input(self, key: str) -> bool:
        return any(t.get("lerobot_key") == key for g in self.io_spec["graphs"] for t in g["inputs"])

    def postprocess(self, action: Array) -> Array:
        feat = self.norm_features.get("action")
        return denormalize(action, feat, self.eps) if feat else action

    # ---- graph execution (normalised space, batched) --------------------------------------
    def _run(self, graph_id: str, feeds: dict[str, Array]) -> Array:
        sess = self.sessions[graph_id]
        names = [i.name for i in sess.get_inputs()]
        result = sess.run(None, {n: feeds[n] for n in names})
        return np.asarray(result[0])

    def predict_chunk(
        self,
        batch: dict[str, Array],
        *,
        sampling_noise: Array | None = None,
        noise_fn: NoiseFn | None = None,
    ) -> Array:
        """Normalised batched inputs (graph shapes) -> normalised action chunk [B, n, A].

        ACT: the full chunk (``chunk_size``). VQ-BeT: ``action_chunk_size`` steps. Diffusion: the
        whole denoised horizon (callers slice ``[n_obs_steps-1 : n_obs_steps-1+n_action_steps]``).
        """
        if self.policy_type == "act":
            return self._run("model", batch)
        if self.policy_type == "vqbet":
            b = next(iter(batch.values())).shape[0]
            spec = next(t for t in self.graphs["model"]["inputs"] if t["role"] == "sampling_noise")
            if sampling_noise is None:
                shape = (b, int(spec["shape"][1]), int(spec["shape"][2]))
                sampling_noise = self.rng.random(shape, dtype=np.float32)
            return self._run("model", {**batch, "sampling_noise": sampling_noise.astype(np.float32)})
        if self.policy_type == "diffusion":
            global_cond = self._run("obs_encoder", batch)
            return self.denoise(global_cond, noise_fn=noise_fn)
        raise ValueError(f"unsupported policy_type {self.policy_type!r}")

    def denoise(self, global_cond: Array, *, noise_fn: NoiseFn | None = None) -> Array:
        """Diffusion sampling loop (``DiffusionModel.conditional_sample``) in numpy."""
        if self.scheduler is None:
            raise RuntimeError("bundle has no diffusion scheduler spec")
        draw: NoiseFn = (
            noise_fn or self.noise_fn or (lambda shape: self.rng.standard_normal(shape, dtype=np.float32))
        )
        horizon = int(self.io_spec["diffusion"]["horizon"])
        b = global_cond.shape[0]
        sample = draw((b, horizon, self.action_dim)).astype(np.float32)
        for i, t in enumerate(self.scheduler.timesteps):
            timestep = np.full((b,), int(t), dtype=np.int64)
            out = self._run(
                "denoiser", {"noisy_action": sample, "timestep": timestep, "global_cond": global_cond}
            )
            sample = self.scheduler.step(out, i, sample, draw)
        return sample

    # ---- rollout API --------------------------------------------------------------------
    def select_action(self, obs: dict[str, Array]) -> Array:
        """One raw observation (no batch dim) -> one raw action ``[A]`` (LeRobot select_action)."""
        x = self.preprocess(obs)
        if self.n_obs_steps > 1 or self.policy_type != "act":
            # lerobot.policies.utils.populate_queues: first call fills the history with copies.
            for key, value in x.items():
                q = self._obs_queue.setdefault(key, deque(maxlen=self.n_obs_steps))
                if len(q) != self.n_obs_steps:
                    while len(q) != self.n_obs_steps:
                        q.append(value)
                else:
                    q.append(value)
        if self.ensembler is not None:
            # LeRobot ACTPolicy.select_action with temporal_ensemble_coeff set (QC-ml-2).
            chunk = self.predict_chunk({k: v[None] for k, v in x.items()})
            return self.postprocess(self.ensembler.update(chunk)[0])
        if not self._action_queue:
            if self.policy_type == "act":
                batch = {k: v[None] for k, v in x.items()}
            else:
                batch = {k: np.stack(list(q), axis=0)[None] for k, q in self._obs_queue.items()}
            chunk = self.predict_chunk(batch)
            if self.policy_type == "diffusion":
                start = self.n_obs_steps - 1
                chunk = chunk[:, start : start + self.n_action_steps]
            else:
                chunk = chunk[:, : self.n_action_steps]
            self._action_queue.extend(chunk[0])
        return self.postprocess(self._action_queue.popleft())


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------
def _random_observation(policy: OnnxPolicy, rng: np.random.Generator) -> dict[str, Array]:
    obs: dict[str, Array] = {}
    for cam in policy.io_spec["cameras"]:
        obs[cam["key"]] = rng.integers(0, 256, size=(cam["height"], cam["width"], 3), dtype=np.uint8)
    state = policy.io_spec.get("state")
    if state:
        feat = policy.norm_features.get(state["key"], {})
        mean = np.asarray(feat.get("mean", np.zeros(state["dim"])), dtype=np.float32)
        obs[state["key"]] = (mean + rng.standard_normal(state["dim"]).astype(np.float32)).astype(np.float32)
    for g in policy.io_spec["graphs"]:
        for t in g["inputs"]:
            if t["role"] == "env_state":
                obs[t["lerobot_key"]] = rng.standard_normal(int(t["shape"][-1])).astype(np.float32)
    return obs


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hibiscus bundle ONNX inference")
    parser.add_argument(
        "--bundle",
        default=str(Path(__file__).resolve().parent.parent),
        help="bundle root or its onnx/ directory",
    )
    parser.add_argument("--selftest", action="store_true", help="run one random observation")
    parser.add_argument("--fp16", action="store_true", help="use model.fp16.onnx if present")
    parser.add_argument("--steps", type=int, default=1, help="select_action calls in the self-test")
    args = parser.parse_args(argv)
    policy = OnnxPolicy(args.bundle, fp16=args.fp16, rng=np.random.default_rng(0))
    if not args.selftest:
        print(json.dumps(policy.io_spec, indent=2))
        return 0
    rng = np.random.default_rng(0)
    obs = _random_observation(policy, rng)
    t0 = time.perf_counter()
    action = policy.select_action(obs)
    first = time.perf_counter() - t0
    for _ in range(max(args.steps - 1, 0)):
        action = policy.select_action(obs)
    print(
        json.dumps(
            {
                "policy_type": policy.policy_type,
                "action": [float(a) for a in action],
                "first_call_latency_ms": round(first * 1000, 2),
            }
        )
    )
    return 0 if bool(np.all(np.isfinite(action))) and action.shape == (policy.action_dim,) else 1


if __name__ == "__main__":
    sys.exit(main())
