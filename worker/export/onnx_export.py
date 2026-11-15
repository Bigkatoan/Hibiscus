"""ONNX export of LeRobot policies (docs/spec/bundle.md §4).

* ACT    -> ``model.onnx``                       (full; VAE latent = zeros, eval path)
* VQ-BeT -> ``model.onnx`` + ``sampling_noise``  (full; inverse-CDF code sampling)
* Diffusion -> ``obs_encoder.onnx`` + ``denoiser.onnx`` (split; the loop lives in infer_onnx.py)

All graphs: opset 17, legacy TorchScript exporter (``dynamo=False``), float32 on CPU,
``do_constant_folding=True``, dynamic axis = batch only. Inputs/outputs are normalised tensors.
"""

from __future__ import annotations

import contextlib
import types
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch
from torch import Tensor, nn

from export.policy_info import ENV_KEY, STATE_KEY, PolicyInfo

OPSET = 17
OBS_IMAGES = "observation.images"


@dataclass(frozen=True)
class TensorSpec:
    name: str
    lerobot_key: str | None
    dtype: str
    shape: list[int | str]
    role: str
    normalized: bool = True

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "lerobot_key": self.lerobot_key,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "role": self.role,
            "normalized": self.normalized,
        }


@dataclass
class GraphSpec:
    id: str
    file: str
    inputs: list[TensorSpec]
    outputs: list[TensorSpec]
    fp16_file: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file": self.file,
            "fp16_file": self.fp16_file,
            "inputs": [t.to_json() for t in self.inputs],
            "outputs": [t.to_json() for t in self.outputs],
        }


class GraphModule(nn.Module):
    """A traceable wrapper whose positional inputs match ``input_specs`` order."""

    graph_id: str = "model"
    input_specs: list[TensorSpec]
    output_specs: list[TensorSpec]

    def example_inputs(self, batch: int = 1) -> tuple[Tensor, ...]:
        out: list[Tensor] = []
        gen = torch.Generator().manual_seed(0)
        for spec in self.input_specs:
            shape = [batch if d == "batch" else int(d) for d in spec.shape]
            if spec.dtype == "int64":
                out.append(torch.randint(0, 10, shape, generator=gen, dtype=torch.long))
            elif spec.role == "sampling_noise":
                out.append(torch.rand(shape, generator=gen))
            else:
                out.append(torch.randn(shape, generator=gen))
        return tuple(out)


@dataclass
class ExportedOnnx:
    graphs: list[GraphSpec]
    modules: dict[str, GraphModule] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)  # non-fatal problems (e.g. fp16 conversion)


# --------------------------------------------------------------------------------------------
# Policy loading
# --------------------------------------------------------------------------------------------
def load_policy_cpu(pretrained_dir: Path, policy_type: str) -> Any:
    """``get_policy_class(type).from_pretrained`` on CPU, float32, eval mode."""
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.policies.factory import get_policy_class

    cls = get_policy_class(policy_type)
    cfg = PreTrainedConfig.from_pretrained(str(pretrained_dir))
    cfg.device = "cpu"
    policy = cls.from_pretrained(str(pretrained_dir), config=cfg)
    policy.to(device="cpu", dtype=torch.float32)
    policy.eval()
    return policy


# --------------------------------------------------------------------------------------------
# Wrappers
# --------------------------------------------------------------------------------------------
def _obs_specs(info: PolicyInfo, with_history: bool) -> list[TensorSpec]:
    hist: list[int | str] = [info.n_obs_steps] if with_history else []
    specs: list[TensorSpec] = []
    state = info.state
    if state is not None:
        specs.append(TensorSpec(state.key, state.key, "float32", ["batch", *hist, *state.shape], "state"))
    for key in info.image_keys:
        feat = info.require_feature(key)
        specs.append(TensorSpec(key, key, "float32", ["batch", *hist, *feat.shape], "image"))
    env = info.env_state
    if env is not None:
        specs.append(TensorSpec(env.key, env.key, "float32", ["batch", *hist, *env.shape], "env_state"))
    return specs


def _split_obs(info: PolicyInfo, args: tuple[Tensor, ...]) -> tuple[dict[str, Tensor], list[Tensor]]:
    batch: dict[str, Tensor] = {}
    images: list[Tensor] = []
    i = 0
    if info.state is not None:
        batch[STATE_KEY] = args[i]
        i += 1
    for _ in info.image_keys:
        images.append(args[i])
        i += 1
    if info.env_state is not None:
        batch[ENV_KEY] = args[i]
        i += 1
    return batch, images


class ACTGraph(GraphModule):
    graph_id = "model"

    def __init__(self, policy: Any, info: PolicyInfo) -> None:
        super().__init__()
        self.model = policy.model
        self.info = info
        self.input_specs = _obs_specs(info, with_history=False)
        chunk = int(policy.config.chunk_size)
        adim = info.action.shape[0]
        self.output_specs = [TensorSpec("action", "action", "float32", ["batch", chunk, adim], "action")]

    def forward(self, *args: Tensor) -> Tensor:
        batch, images = _split_obs(self.info, args)
        if images:
            batch[OBS_IMAGES] = images  # type: ignore[assignment]  # ACT takes a list of [B,3,H,W]
        out: Tensor = self.model(batch)[0]
        return out


class DiffusionObsEncoderGraph(GraphModule):
    graph_id = "obs_encoder"

    def __init__(self, policy: Any, info: PolicyInfo) -> None:
        super().__init__()
        self.diffusion = policy.diffusion
        self.info = info
        self.input_specs = _obs_specs(info, with_history=True)
        self.output_specs = []
        with torch.no_grad():
            gdim = int(self.forward(*self.example_inputs(1)).shape[-1])
        self.global_cond_dim = gdim
        self.output_specs = [TensorSpec("global_cond", None, "float32", ["batch", gdim], "global_cond")]

    def forward(self, *args: Tensor) -> Tensor:
        batch, images = _split_obs(self.info, args)
        if images:
            batch[OBS_IMAGES] = torch.stack(images, dim=-4)  # [B, S, N, C, H, W]
        out: Tensor = self.diffusion._prepare_global_conditioning(batch)
        return out


class DiffusionDenoiserGraph(GraphModule):
    graph_id = "denoiser"

    def __init__(self, policy: Any, info: PolicyInfo, global_cond_dim: int) -> None:
        super().__init__()
        self.unet = policy.diffusion.unet
        horizon = int(policy.config.horizon)
        adim = info.action.shape[0]
        self.input_specs = [
            TensorSpec("noisy_action", None, "float32", ["batch", horizon, adim], "noisy_action"),
            TensorSpec("timestep", None, "int64", ["batch"], "timestep", normalized=False),
            TensorSpec("global_cond", None, "float32", ["batch", global_cond_dim], "global_cond"),
        ]
        self.output_specs = [
            TensorSpec("model_output", None, "float32", ["batch", horizon, adim], "model_output")
        ]

    def forward(self, noisy_action: Tensor, timestep: Tensor, global_cond: Tensor) -> Tensor:
        out: Tensor = self.unet(noisy_action, timestep, global_cond=global_cond)
        return out


def inverse_cdf_sample(probs: Tensor, u: Tensor) -> Tensor:
    """``code = argmax(cumsum(probs) > u)`` with the last bin as a catch-all; returns [R, 1] int64."""
    cdf = probs.cumsum(dim=-1)
    above = cdf > u.unsqueeze(-1)
    last = torch.ones_like(above[:, :1])
    above = torch.cat([above[:, :-1], last], dim=-1)
    return torch.argmax(above.to(torch.int32), dim=-1, keepdim=True).to(torch.long)


class _TorchProxy(types.ModuleType):
    """Stands in for ``torch`` inside modeling_vqbet, replacing only ``multinomial``."""

    def __init__(self, real: types.ModuleType, multinomial: Any) -> None:
        super().__init__("torch")
        self._real = real
        self.multinomial = multinomial

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


@contextlib.contextmanager
def vqbet_inverse_cdf(u_full: Tensor, sequential: bool) -> Iterator[None]:
    """Patch ``torch.multinomial`` in modeling_vqbet with inverse-CDF sampling driven by ``u_full``.

    ``u_full``: [N, T, G] uniforms, row order matches VQBeTHead's ``(N T)`` / ``(NT G)`` layout.
    """
    from lerobot.policies.vqbet import modeling_vqbet as mv

    calls = {"n": 0}

    def multinomial(probs: Tensor, num_samples: int = 1, **_: Any) -> Tensor:
        if num_samples != 1:
            raise ValueError("vqbet export expects num_samples=1")
        if sequential:
            u = u_full[..., calls["n"]].reshape(-1)
        else:
            u = u_full.reshape(-1)
        calls["n"] += 1
        return inverse_cdf_sample(probs, u)

    real = mv.torch
    mv.torch = _TorchProxy(real, multinomial)
    try:
        yield
    finally:
        mv.torch = real


class VQBeTGraph(GraphModule):
    graph_id = "model"

    def __init__(self, policy: Any, info: PolicyInfo) -> None:
        super().__init__()
        self.vqbet = policy.vqbet
        self.info = info
        cfg = policy.config
        self.n_obs_steps = int(cfg.n_obs_steps)
        self.n_action_pred_token = int(cfg.n_action_pred_token)
        self.chunk = int(cfg.action_chunk_size)
        self.n_layers = int(self.vqbet.action_head.vqvae_model.vqvae_num_layers)
        self.sequential = bool(cfg.sequentially_select)
        adim = info.action.shape[0]
        self.input_specs = [
            *_obs_specs(info, with_history=True),
            TensorSpec(
                "sampling_noise",
                None,
                "float32",
                ["batch", self.n_action_pred_token, self.n_layers],
                "sampling_noise",
                normalized=False,
            ),
        ]
        self.output_specs = [TensorSpec("action", "action", "float32", ["batch", self.chunk, adim], "action")]

    def forward(self, *args: Tensor) -> Tensor:
        noise = args[-1]
        batch, images = _split_obs(self.info, args[:-1])
        batch[OBS_IMAGES] = torch.stack(images, dim=-4)
        # History tokens (all but the current step) are computed but discarded in rollout: fixed u.
        hist = torch.full_like(noise[:, :1, :], 0.5).expand(-1, self.n_obs_steps - 1, -1)
        u_full = torch.cat([hist, noise], dim=1)
        with vqbet_inverse_cdf(u_full, self.sequential):
            out: Tensor = self.vqbet(batch, rollout=True)[:, : self.chunk]
        return out


class StaticCenterCrop(nn.Module):
    """``torchvision.transforms.CenterCrop`` with offsets fixed at build time.

    torchvision computes ``int(round((H - h) / 2))`` from the runtime shape, which the ONNX tracer
    turns into a tensor (``TypeError: type Tensor doesn't define __round__``). Input sizes are
    static in our graphs, so the same offsets are precomputed (bit-identical slicing).
    """

    def __init__(self, in_hw: tuple[int, int], crop_hw: tuple[int, int]) -> None:
        super().__init__()
        (h, w), (ch, cw) = in_hw, crop_hw
        if ch > h or cw > w:
            raise ValueError(f"crop {crop_hw} larger than input {in_hw} (padding crop not supported)")
        self.top = round((h - ch) / 2.0)  # same banker's rounding as torchvision
        self.left = round((w - cw) / 2.0)
        self.ch, self.cw = ch, cw

    def forward(self, x: Tensor) -> Tensor:
        return x[..., self.top : self.top + self.ch, self.left : self.left + self.cw]


def make_crops_static(policy: Any, info: PolicyInfo) -> int:
    """Swap every eval-path ``CenterCrop`` in the policy for :class:`StaticCenterCrop`; returns count."""
    import torchvision

    keys = info.image_keys
    if not keys:
        return 0
    feat = info.require_feature(keys[0])
    image_hw = (int(feat.shape[-2]), int(feat.shape[-1]))
    n = 0
    for module in policy.modules():
        crop = getattr(module, "center_crop", None)
        if isinstance(crop, torchvision.transforms.CenterCrop):
            size = crop.size if isinstance(crop.size, (tuple, list)) else (crop.size, crop.size)
            resize = getattr(module, "resize", None)
            in_hw = tuple(int(s) for s in resize.size) if resize is not None else image_hw
            static = StaticCenterCrop((in_hw[0], in_hw[1]), (int(size[0]), int(size[-1])))
            if getattr(module, "maybe_random_crop", None) is crop:
                module.maybe_random_crop = static
            module.center_crop = static
            n += 1
    return n


def build_graph_modules(policy: Any, info: PolicyInfo) -> list[GraphModule]:
    make_crops_static(policy, info)
    if info.policy_type == "act":
        return [ACTGraph(policy, info)]
    if info.policy_type == "vqbet":
        return [VQBeTGraph(policy, info)]
    if info.policy_type == "diffusion":
        enc = DiffusionObsEncoderGraph(policy, info)
        return [enc, DiffusionDenoiserGraph(policy, info, enc.global_cond_dim)]
    raise ValueError(f"policy type {info.policy_type!r} has no ONNX export in v1")


# --------------------------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------------------------
def export_graph(module: GraphModule, path: Path) -> None:
    names_in = [s.name for s in module.input_specs]
    names_out = [s.name for s in module.output_specs]
    dynamic = {n: {0: "batch"} for n in (*names_in, *names_out)}
    module.eval()
    with torch.no_grad():
        torch.onnx.export(
            module,
            module.example_inputs(1),
            str(path),
            input_names=names_in,
            output_names=names_out,
            opset_version=OPSET,
            dynamo=False,
            do_constant_folding=True,
            dynamic_axes=dynamic,
        )
    import onnx

    onnx.checker.check_model(str(path))


def convert_fp16(src: Path, dst: Path) -> None:
    """float16 weights/compute, float32 graph I/O (keep_io_types) so io_spec stays valid."""
    import onnx
    import onnxruntime as ort
    from onnx import TensorProto
    from onnxconverter_common import float16

    model = onnx.load(str(src))
    half = float16.convert_float_to_float16(model, keep_io_types=True, disable_shape_infer=False)
    # onnxconverter-common retypes the outputs of explicit ``Cast(to=FLOAT)`` nodes (e.g. ACT's
    # ``torch.zeros(...).to(float32)`` latent) to float16 but leaves ``to`` unchanged, which
    # onnxruntime rejects. Retarget those casts; graph-output casts (keep_io_types) stay float32.
    value_types = {v.name: v.type.tensor_type.elem_type for v in half.graph.value_info}
    graph_outputs = {o.name for o in half.graph.output}
    for node in half.graph.node:
        if node.op_type != "Cast" or node.output[0] in graph_outputs:
            continue
        for attr in node.attribute:
            if (
                attr.name == "to"
                and attr.i == TensorProto.FLOAT
                and value_types.get(node.output[0]) == TensorProto.FLOAT16
            ):
                attr.i = TensorProto.FLOAT16
    onnx.save(half, str(dst))
    ort.InferenceSession(str(dst), providers=["CPUExecutionProvider"])  # must load, else raise


def export_onnx(policy: Any, info: PolicyInfo, out_dir: Path, *, fp16: bool = False) -> ExportedOnnx:
    """Export all graphs of ``policy`` into ``out_dir``; returns their specs and torch wrappers."""
    out_dir.mkdir(parents=True, exist_ok=True)
    modules = build_graph_modules(policy, info)
    graphs: list[GraphSpec] = []
    notes: list[str] = []
    for mod in modules:
        fname = f"{mod.graph_id}.onnx"
        export_graph(mod, out_dir / fname)
        spec = GraphSpec(mod.graph_id, fname, list(mod.input_specs), list(mod.output_specs))
        if fp16 and info.onnx_support == "full":
            fp16_name = f"{mod.graph_id}.fp16.onnx"
            try:
                convert_fp16(out_dir / fname, out_dir / fp16_name)
                spec.fp16_file = fp16_name
            except Exception as exc:  # fp16 is optional and informational: never fail the export
                (out_dir / fp16_name).unlink(missing_ok=True)
                notes.append(f"fp16 conversion of {fname} failed: {type(exc).__name__}: {exc}")
        graphs.append(spec)
    return ExportedOnnx(graphs=graphs, modules={m.graph_id: m for m in modules}, notes=notes)
