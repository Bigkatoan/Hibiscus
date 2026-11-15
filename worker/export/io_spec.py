"""Build ``onnx/io_spec.json`` (docs/spec/bundle.md §4, schema io_spec.schema.json)."""

from __future__ import annotations

from typing import Any

from export.onnx_export import OPSET, GraphSpec
from export.policy_info import PolicyInfo


def diffusion_spec(cfg: dict[str, Any]) -> dict[str, Any]:
    n_train = int(cfg["num_train_timesteps"])
    n_inf = cfg.get("num_inference_steps")
    return {
        "scheduler": str(cfg["noise_scheduler_type"]),
        "num_train_timesteps": n_train,
        "num_inference_steps": int(n_inf) if n_inf is not None else n_train,
        "beta_schedule": str(cfg["beta_schedule"]),
        "beta_start": float(cfg["beta_start"]),
        "beta_end": float(cfg["beta_end"]),
        "prediction_type": str(cfg["prediction_type"]),
        "clip_sample": bool(cfg["clip_sample"]),
        "clip_sample_range": float(cfg["clip_sample_range"]),
        "horizon": int(cfg["horizon"]),
    }


def temporal_ensemble_coeff(info: PolicyInfo) -> float | None:
    if info.policy_type != "act":
        return None
    coeff = info.raw.get("temporal_ensemble_coeff")
    return None if coeff is None else float(coeff)


def build_io_spec(
    *,
    info: PolicyInfo,
    graphs: list[GraphSpec],
    fps: float,
    state_names: list[str],
    action_names: list[str],
    camera_codecs: dict[str, str | None],
) -> dict[str, Any]:
    if info.onnx_support == "none":
        raise ValueError(f"{info.policy_type} has no ONNX graphs")
    cameras = []
    for key in info.image_keys:
        _, h, w = info.require_feature(key).shape
        cameras.append(
            {
                "key": key,
                "input_name": key,
                "height": int(h),
                "width": int(w),
                "channels_order": "RGB",
                "source_codec": camera_codecs.get(key),
            }
        )
    state = info.state
    action = info.action
    chunk, steps = info.chunk_size, info.n_action_steps
    if chunk is None or steps is None:
        raise ValueError(f"{info.policy_type}: chunk size / n_action_steps missing from config.json")
    with_history = info.policy_type in ("diffusion", "vqbet")
    steps_pre = ["to_float32", "divide_255", "hwc_to_chw", "normalize", "add_batch_dim"]
    if with_history:
        steps_pre.append("stack_obs_steps")
    return {
        "schema_version": "1",
        "policy_type": info.policy_type,
        "onnx_support": info.onnx_support,
        "opset": OPSET,
        "fps": fps,
        "n_obs_steps": info.n_obs_steps,
        "graphs": [g.to_json() for g in graphs],
        "cameras": cameras,
        "state": (
            {"key": state.key, "dim": int(state.shape[0]), "names": list(state_names)}
            if state is not None
            else None
        ),
        "action": {
            "key": "action",
            "dim": int(action.shape[0]),
            "names": list(action_names),
            "chunk_size": int(chunk),
            "n_action_steps": int(steps),
            # QC-ml-2: the ONNX runner must blend chunks exactly like LeRobot's ACT select_action.
            "temporal_ensemble_coeff": temporal_ensemble_coeff(info),
        },
        "normalization_file": "normalization.json",
        "image_preprocess": {"input": "uint8 HWC RGB frame as decoded from the camera", "steps": steps_pre},
        "diffusion": diffusion_spec(info.raw) if info.policy_type == "diffusion" else None,
    }
