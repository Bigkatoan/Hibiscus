"""Re-verification of an existing bundle zip (OpenAPI ``reverifyModel``; docs/spec/bundle.md §10).

Re-runs the three checks against the *delivered* artefact: MANIFEST hashes of the zip, LeRobot load
of ``pretrained_model/`` in a fresh interpreter, and ONNX parity of the bundle's own ``onnx/*.onnx``
files (not a re-export) against the PyTorch policy loaded from the same bundle.
"""

from __future__ import annotations

import json
import logging
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.pretrained_guard import UntrustedPretrainedError, validate_pretrained_dir
from export.lelab_compat import extra_requirements, pip_command
from export.load_check import run_load_checks
from export.manifest import verify_zip
from export.onnx_export import ExportedOnnx, GraphSpec, TensorSpec
from export.policy_info import load_policy_info
from export.types import Verification, is_verified

log = logging.getLogger("hibiscus.export")


def _graph_specs(io_spec: dict[str, Any]) -> list[GraphSpec]:
    def tensors(items: list[dict[str, Any]]) -> list[TensorSpec]:
        return [
            TensorSpec(
                t["name"],
                t.get("lerobot_key"),
                t["dtype"],
                list(t["shape"]),
                t["role"],
                t.get("normalized", True),
            )
            for t in items
        ]

    return [
        GraphSpec(g["id"], g["file"], tensors(g["inputs"]), tensors(g["outputs"]), g.get("fp16_file"))
        for g in io_spec["graphs"]
    ]


def reparity(
    bundle_dir: Path, *, dataset_root: Path, repo_id: str, heldout_episodes: list[int], n_samples: int = 32
) -> dict[str, Any]:
    """Parity of the bundle's ONNX files vs the bundle's PyTorch policy (fresh samples, seed 0)."""
    from export.onnx_export import build_graph_modules, load_policy_cpu
    from export.parity import run_parity
    from export.samples import draw_parity_samples, load_processors

    onnx_dir = bundle_dir / "onnx"
    pm = bundle_dir / "pretrained_model"
    io_spec: dict[str, Any] = json.loads((onnx_dir / "io_spec.json").read_text())
    normalization: dict[str, Any] = json.loads((onnx_dir / "normalization.json").read_text())
    info = load_policy_info(pm)
    policy = load_policy_cpu(pm, info.policy_type)
    modules = {m.graph_id: m for m in build_graph_modules(policy, info)}
    specs = _graph_specs(io_spec)
    for spec in specs:
        expected = [t.name for t in modules[spec.id].input_specs]
        if [t.name for t in spec.inputs] != expected:
            raise ValueError(
                f"{spec.file}: io_spec inputs {[t.name for t in spec.inputs]} != policy {expected}"
            )
    pre, _ = load_processors(pm, "cpu")
    samples = draw_parity_samples(
        dataset_root=dataset_root,
        repo_id=repo_id,
        heldout_episodes=heldout_episodes,
        info=info,
        preprocessor=pre,
        fps=float(io_spec["fps"]),
        n_samples=n_samples,
        seed=0,
    )
    return run_parity(
        policy=policy,
        info=info,
        exported=ExportedOnnx(graphs=specs, modules=modules),
        onnx_dir=onnx_dir,
        samples=samples,
        normalization=normalization,
        io_spec=io_spec,
        seed=0,
    )


def reverify_bundle(
    zip_path: Path,
    *,
    dataset_root: Path,
    repo_id: str,
    heldout_episodes: list[int],
    onnx_requested: bool = True,
    load_check_python: str | None = None,
    n_samples: int = 32,
) -> tuple[Verification, bool]:
    """Re-run load / parity / manifest checks on a produced ``<bundle_name>.zip``.

    Returns ``(verification, verified)`` for ``models.verification`` / ``models.verified``.
    """
    details: list[str] = []
    mcheck = verify_zip(zip_path)
    if not mcheck.ok:
        details.append(f"manifest: {mcheck.detail}")
    with tempfile.TemporaryDirectory(prefix="hibiscus-reverify-") as tmp:
        with zipfile.ZipFile(zip_path) as zf:
            top = zf.namelist()[0].split("/", 1)[0]
            members = [n for n in zf.namelist() if n.startswith(f"{top}/") and ".." not in n.split("/")]
            zf.extractall(tmp, members=members)  # members filtered above
        bundle_dir = Path(tmp) / top
        # SEC-input-1: never let LeRobot load a processor JSON outside the allow-list.
        try:
            validate_pretrained_dir(bundle_dir / "pretrained_model", require_processors=False)
        except UntrustedPretrainedError as exc:
            v = Verification(
                load_ok=False,
                parity_ok=None,
                manifest_ok=mcheck.ok,
                checked_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                details="; ".join([*details, f"load: rejected: {exc}"]),
                lelab_compatible=False,
            )
            return v, False
        info = load_policy_info(bundle_dir / "pretrained_model")
        episode = sorted(heldout_episodes)[0] if heldout_episodes else 0
        lc, lelab_lc = run_load_checks(
            bundle_dir / "pretrained_model",
            dataset_root=dataset_root,
            repo_id=repo_id,
            episode=episode,
            lelab_python=load_check_python,
        )
        if not lc.ok:
            details.append(f"load: {lc.detail}")
        elif not lelab_lc.ok:
            reqs = extra_requirements(info.policy_type, peft=bool(info.peft))
            hint = f"; install first: {pip_command(reqs)}" if reqs else ""
            details.append(f"LeLab venv: does not load without extra packages ({lelab_lc.detail}){hint}")
        parity_ok: bool | None = None
        parity_summary: dict[str, Any] | None = None
        if info.onnx_support != "none" and onnx_requested:
            if not (bundle_dir / "onnx" / "io_spec.json").is_file():
                parity_ok = False
                details.append("parity: bundle has no onnx/ directory")
            else:
                try:
                    report = reparity(
                        bundle_dir,
                        dataset_root=dataset_root,
                        repo_id=repo_id,
                        heldout_episodes=heldout_episodes,
                        n_samples=n_samples,
                    )
                    parity_ok = bool(report["passed"])
                    gating = [g for g in report["graphs"] if g["gating"]]
                    worst = max(gating, key=lambda g: g["max_abs_diff"] / g["atol"])
                    parity_summary = {
                        "max_abs_diff": worst["max_abs_diff"],
                        "atol": worst["atol"],
                        "rtol": worst["rtol"],
                        "n_samples": report["n_samples"],
                    }
                    if not parity_ok:
                        details.append("parity: above threshold")
                except Exception as exc:
                    log.exception("re-parity failed")
                    parity_ok = False
                    details.append(f"parity: {type(exc).__name__}: {exc}")
    verification = Verification(
        load_ok=lc.ok,
        parity_ok=parity_ok,
        manifest_ok=mcheck.ok,
        checked_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        parity=parity_summary,
        details="; ".join(details) or None,
        lelab_compatible=lelab_lc.ok,
    )
    verified = is_verified(
        load_ok=lc.ok,
        manifest_ok=mcheck.ok,
        parity_ok=parity_ok,
        onnx_support=info.onnx_support,
        onnx_requested=onnx_requested,
    )
    log.info("reverified %s verified=%s", zip_path.name, verified)
    return verification, verified
