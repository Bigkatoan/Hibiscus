"""Bundle builder (PLAN §3.6, docs/spec/bundle.md): checkpoint -> verified ``<bundle_name>.zip``.

Entry point for the A4 worker: :func:`build_bundle` (pure function of a :class:`BundleRequest`;
no DB / S3 / Redis access — the caller downloads the checkpoint, uploads the zip and records the
returned :class:`BundleResult`).
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import time
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from core.pretrained_guard import validate_pretrained_dir
from export.lelab_compat import extra_requirements, pip_command
from export.logs import write_metrics_csv, write_train_log
from export.manifest import copy_tree_exact, verify_zip, write_manifest, zip_bundle
from export.model_card import CardContext, render_model_card
from export.normalization import build_normalization
from export.policy_info import PolicyInfo, load_policy_info
from export.run_on_robot import CameraSpec, render_run_on_robot
from export.types import (
    BundleRequest,
    BundleResult,
    ManifestOnnxStatus,
    Verification,
    bundle_name,
    default_model_name,
    is_verified,
)

log = logging.getLogger("hibiscus.export")
TEMPLATES = Path(__file__).resolve().parent / "templates"


def _version(dist: str) -> str | None:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return None


def software_info(image_digest: str) -> dict[str, Any]:
    import torch

    return {
        "lerobot": _version("lerobot") or "unknown",
        "torch": str(torch.__version__),
        "cuda": torch.version.cuda,
        "python": platform.python_version(),
        "onnx": _version("onnx"),
        "onnxruntime": _version("onnxruntime"),
        "image_digest": image_digest,
    }


def dataset_meta(root: Path, repo_id: str) -> dict[str, Any]:
    """robot_type, fps, camera keys/shapes/codecs, state/action names and tasks of a dataset version."""
    from lerobot.datasets.lerobot_dataset import LeRobotDatasetMetadata

    meta = LeRobotDatasetMetadata(repo_id, root=root)
    feats: dict[str, Any] = meta.features
    cams = [k for k, v in feats.items() if v.get("dtype") in ("video", "image")]
    codecs = {k: (feats[k].get("info") or {}).get("video.codec") for k in cams}
    sizes = {}
    for k in cams:
        shape = feats[k]["shape"]
        names = feats[k].get("names") or ["height", "width", "channels"]
        dims = dict(zip(names, shape, strict=False))
        sizes[k] = (int(dims.get("width", shape[1])), int(dims.get("height", shape[0])))
    tasks = [str(t) for t in meta.tasks.index] if meta.tasks is not None else []
    return {
        "robot_type": meta.robot_type,
        "fps": float(meta.fps),
        "camera_keys": cams,
        "camera_codecs": codecs,
        "camera_sizes": sizes,
        "state_names": list((feats.get("observation.state") or {}).get("names") or []),
        "action_names": list((feats.get("action") or {}).get("names") or []),
        "tasks": tasks,
    }


def policy_config_defaults(policy_type: str) -> dict[str, Any] | None:
    try:
        import draccus
        from lerobot.policies.factory import make_policy_config

        encoded = draccus.encode(make_policy_config(policy_type))
        return dict(encoded) if isinstance(encoded, dict) else None
    except Exception:  # defaults are cosmetic (model card table) — never fail the export for them
        log.warning("could not resolve LeRobot defaults for %s", policy_type, exc_info=True)
        return None


def run_onnx_stage(
    *,
    pretrained_dir: Path,
    policy: Any,
    info: PolicyInfo,
    meta: dict[str, Any],
    onnx_dir: Path,
    dataset_root: Path,
    repo_id: str,
    heldout_episodes: list[int],
    fp16: bool = False,
    n_samples: int = 32,
) -> tuple[ManifestOnnxStatus, str | None, dict[str, Any] | None]:
    """Export graphs + io_spec/normalization/infer_onnx.py/requirements.txt into ``onnx_dir`` and run
    parity. Returns (onnx_status, detail, parity_report). On an export/parity *crash* ``onnx_dir`` is
    removed (status ``failed``); on a parity *miss* it is kept with ``parity_report.passed = false``."""
    from export.io_spec import build_io_spec
    from export.onnx_export import export_onnx
    from export.parity import run_parity
    from export.samples import draw_parity_samples, load_processors

    onnx_dir.mkdir(parents=True, exist_ok=True)
    try:
        exported = export_onnx(policy, info, onnx_dir, fp16=fp16)
        normalization = build_normalization(pretrained_dir, info)
        io_spec = build_io_spec(
            info=info,
            graphs=exported.graphs,
            fps=meta["fps"],
            state_names=meta["state_names"],
            action_names=meta["action_names"],
            camera_codecs=meta["camera_codecs"],
        )
        (onnx_dir / "normalization.json").write_text(json.dumps(normalization, indent=2) + "\n")
        (onnx_dir / "io_spec.json").write_text(json.dumps(io_spec, indent=2) + "\n")
        shutil.copyfile(TEMPLATES / "infer_onnx.py", onnx_dir / "infer_onnx.py")
        os.chmod(onnx_dir / "infer_onnx.py", 0o755)  # noqa: S103  # spec §1: *.py are 0755
        ort_v = _version("onnxruntime") or "1.20.0"
        (onnx_dir / "requirements.txt").write_text(
            f"numpy>=1.24\nonnxruntime=={ort_v}\nopencv-python-headless>=4.9\n"
        )
    except Exception as exc:
        shutil.rmtree(onnx_dir, ignore_errors=True)
        log.exception("ONNX export failed")
        return "failed", f"export: {type(exc).__name__}: {exc}", None
    try:
        pre, _ = load_processors(pretrained_dir, "cpu")
        samples = draw_parity_samples(
            dataset_root=dataset_root,
            repo_id=repo_id,
            heldout_episodes=heldout_episodes,
            info=info,
            preprocessor=pre,
            fps=meta["fps"],
            n_samples=n_samples,
            seed=0,
        )
        report = run_parity(
            policy=policy,
            info=info,
            exported=exported,
            onnx_dir=onnx_dir,
            samples=samples,
            normalization=normalization,
            io_spec=io_spec,
            seed=0,
        )
    except Exception as exc:
        # onnx/ is shipped only together with its parity_report.json (CR-A5-2)
        log.exception("ONNX parity failed to run")
        shutil.rmtree(onnx_dir, ignore_errors=True)
        return "failed", f"parity: {type(exc).__name__}: {exc}", None
    (onnx_dir / "parity_report.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["passed"]:
        return "passed", "; ".join(exported.notes) or None, report
    bad = [g["comparison"] for g in report["graphs"] if g["gating"] and not g["passed"]]
    return "failed", f"parity above threshold: {', '.join(bad)}", report


def build_bundle(req: BundleRequest) -> BundleResult:
    """Build, zip and verify the bundle. Raises only on infrastructure errors (missing checkpoint,
    unreadable dataset, disk); ONNX / parity / eval / load problems are reported in the result."""
    # SEC-input-1 / phase-5 N4: the checkpoint was written by the training child. Validate its
    # processor JSON BEFORE anything below hands the directory to LeRobot (load_policy_cpu,
    # load_processors and evaluate_heldout all run ``PolicyProcessorPipeline.from_pretrained``).
    validate_pretrained_dir(req.pretrained_dir, require_processors=False)
    timings: dict[str, float] = {}
    t_all = time.monotonic()
    created_at = req.created_at or datetime.now(UTC)
    info = load_policy_info(req.pretrained_dir)
    model_name = req.options.model_name or default_model_name(req.dataset.name, info.policy_type)
    name = bundle_name(model_name, req.run.number, req.checkpoint_step)
    bundle_dir = req.work_dir / name
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True)
    details: list[str] = []

    abort = req.abort_check or (lambda: None)
    abort()
    copy_tree_exact(req.pretrained_dir, bundle_dir / "pretrained_model")
    meta = dataset_meta(req.dataset.root, req.dataset.repo_id)

    # ---- ONNX (CPU) -----------------------------------------------------------------------
    onnx_status: ManifestOnnxStatus
    onnx_detail: str | None = None
    parity_report: dict[str, Any] | None = None
    policy: Any = None
    t = time.monotonic()
    if info.onnx_support == "none":
        onnx_status = "not_supported"
        onnx_detail = f"{info.policy_type}: no ONNX export in v1"
    elif not req.options.onnx:
        onnx_status = "skipped"
    else:
        from export.onnx_export import load_policy_cpu

        policy = load_policy_cpu(bundle_dir / "pretrained_model", info.policy_type)
        onnx_status, onnx_detail, parity_report = run_onnx_stage(
            pretrained_dir=bundle_dir / "pretrained_model",
            policy=policy,
            info=info,
            meta=meta,
            onnx_dir=bundle_dir / "onnx",
            dataset_root=req.dataset.root,
            repo_id=req.dataset.repo_id,
            heldout_episodes=req.training.heldout_episodes,
            fp16=req.options.onnx_fp16,
            n_samples=req.parity_samples,
        )
    timings["onnx_s"] = time.monotonic() - t
    if onnx_detail and onnx_status == "failed":
        details.append(onnx_detail)
    abort()

    # ---- offline eval ---------------------------------------------------------------------
    eval_metrics: dict[str, Any] | None = None
    t = time.monotonic()
    if req.options.eval and req.training.heldout_episodes:
        from eval.offline import evaluate_heldout

        try:
            eval_metrics = evaluate_heldout(
                pretrained_dir=bundle_dir / "pretrained_model",
                dataset_root=req.dataset.root,
                repo_id=req.dataset.repo_id,
                heldout_episodes=req.training.heldout_episodes,
                run_id=req.run.id,
                step=req.checkpoint_step,
                out_dir=bundle_dir / "eval",
                device=req.eval_device,
                policy=policy,
            )
        except Exception as exc:
            log.exception("offline eval failed")
            shutil.rmtree(bundle_dir / "eval", ignore_errors=True)
            details.append(f"eval: {type(exc).__name__}: {exc}")
    timings["eval_s"] = time.monotonic() - t
    del policy
    abort()

    # ---- logs -----------------------------------------------------------------------------
    write_train_log(req.train_logs, bundle_dir / "logs" / "train.log")
    write_metrics_csv(req.metrics, bundle_dir / "logs" / "metrics.csv")

    # ---- load check (fresh interpreter) ---------------------------------------------------
    from export.load_check import run_load_checks

    t = time.monotonic()
    episode = sorted(req.training.heldout_episodes)[0] if req.training.heldout_episodes else 0
    # QC-ml-1: load the bundle the way the user will, in the LeLab venv (a real LeLab interpreter
    # when configured, otherwise this interpreter with LeLab's missing extras hidden). load_ok
    # (needed for "verified") means "LeRobot 0.7.1 loads it"; lelab_compatible says whether it
    # loads without extra packages.
    lelab_env = "lelab_venv" if req.load_check_python else "emulated"
    lc, lelab_lc = run_load_checks(
        bundle_dir / "pretrained_model",
        dataset_root=req.dataset.root,
        repo_id=req.dataset.repo_id,
        episode=episode,
        lelab_python=req.load_check_python,
    )
    lelab_ok = lelab_lc.ok
    requirements = [] if lelab_ok else extra_requirements(info.policy_type, peft=bool(info.peft))
    timings["load_check_s"] = time.monotonic() - t
    if not lc.ok:
        details.append(f"load: {lc.detail}")
    elif not lelab_ok:
        hint = f"; install first: {pip_command(requirements)}" if requirements else ""
        details.append(f"LeLab venv: does not load without extra packages ({lelab_lc.detail}){hint}")
    abort()
    parity_ok: bool | None = (
        None
        if parity_report is None and onnx_status != "failed"
        else bool(parity_report and parity_report["passed"])
    )

    # ---- run_on_robot.sh + MODEL_CARD.md ----------------------------------------------------
    cameras = [
        CameraSpec(key=k, width=meta["camera_sizes"][k][0], height=meta["camera_sizes"][k][1])
        for k in info.image_keys
        if k in meta["camera_sizes"]
    ]
    script = render_run_on_robot(
        bundle_name=name,
        robot_type=meta["robot_type"],
        fps=meta["fps"],
        cameras=cameras,
        task=meta["tasks"][0] if meta["tasks"] else "",
        requirements=requirements,
    )
    (bundle_dir / "run_on_robot.sh").write_text(script)
    os.chmod(bundle_dir / "run_on_robot.sh", 0o755)  # noqa: S103  # spec §1: *.sh are 0755
    software = software_info(req.image_digest)
    provisional_verified = is_verified(
        load_ok=lc.ok,
        manifest_ok=True,
        parity_ok=parity_ok,
        onnx_support=info.onnx_support,
        onnx_requested=req.options.onnx,
    )
    card = render_model_card(
        CardContext(
            bundle_name=name,
            policy_type=info.policy_type,
            dataset_name=req.dataset.name,
            dataset_version=req.dataset.version,
            dataset_repo_id=req.dataset.repo_id,
            dataset_content_hash=req.dataset.content_hash,
            checkpoint_step=req.checkpoint_step,
            verified=provisional_verified,
            load_ok=lc.ok,
            parity_ok=parity_ok,
            onnx_status=onnx_status,
            onnx_support=info.onnx_support,
            lelab_compatible=lelab_ok,
            lelab_check=lelab_env,
            lelab_requirements=requirements,
            run_name=req.run.name,
            run_number=req.run.number,
            seed=req.training.seed,
            total_steps=req.training.total_steps,
            batch_size=req.training.batch_size,
            mixed_precision=req.training.mixed_precision,
            gpu_name=req.training.gpu_name,
            gpu_seconds=req.training.gpu_seconds,
            heldout_episodes=req.training.heldout_episodes,
            train_episodes=req.training.train_episodes,
            final_loss=req.training.final_loss,
            software=software,
            config=info.raw,
            config_defaults=policy_config_defaults(info.policy_type),
            eval_metrics=eval_metrics,
            parity_report=parity_report,
            fps=meta["fps"],
            tasks=meta["tasks"],
        )
    )
    (bundle_dir / "MODEL_CARD.md").write_text(card)

    # ---- MANIFEST.json (last) -------------------------------------------------------------
    manifest = write_manifest(
        bundle_dir,
        {
            "schema_version": "1",
            "bundle_name": name,
            "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hibiscus_version": req.hibiscus_version,
            "model_id": req.model_id,
            "run": {
                "id": req.run.id,
                "number": req.run.number,
                "name": req.run.name,
                "workspace_id": req.run.workspace_id,
            },
            "checkpoint_step": req.checkpoint_step,
            "policy": {
                "type": info.policy_type,
                "onnx_support": info.onnx_support,
                "chunk_size": info.chunk_size,
                "n_action_steps": info.n_action_steps,
                "peft": info.peft,
            },
            "dataset": {
                "dataset_id": req.dataset.dataset_id,
                "version_id": req.dataset.version_id,
                "version": req.dataset.version,
                "name": req.dataset.name,
                "content_hash": req.dataset.content_hash,
                "repo_id": req.dataset.repo_id,
                "robot_type": meta["robot_type"],
                "fps": meta["fps"],
                "camera_keys": meta["camera_keys"],
                "state_names": meta["state_names"],
                "action_names": meta["action_names"],
                "tasks": meta["tasks"],
            },
            "software": software,
            "training": {
                "seed": req.training.seed,
                "total_steps": req.training.total_steps,
                "batch_size": req.training.batch_size,
                "mixed_precision": req.training.mixed_precision,
                "gpu_name": req.training.gpu_name,
                "heldout_episodes": list(req.training.heldout_episodes),
                "train_episodes": list(req.training.train_episodes),
                "gpu_seconds": float(req.training.gpu_seconds),
                "final_loss": req.training.final_loss,
            },
            "checks": {
                "load_ok": lc.ok,
                "lelab_compatible": lelab_ok,
                "lelab_check": lelab_env,
                "lelab_requirements": requirements,
                "parity_ok": parity_ok,
                "onnx_status": onnx_status,
                "eval": (
                    {
                        "action_mae": eval_metrics["overall"]["mae"],
                        "action_mse": eval_metrics["overall"]["mse"],
                    }
                    if eval_metrics
                    else None
                ),
            },
        },
    )

    # ---- zip + manifest_ok ----------------------------------------------------------------
    abort()
    t = time.monotonic()
    zip_path = req.work_dir / f"{name}.zip"
    zip_sha = zip_bundle(bundle_dir, zip_path, date_time=created_at)
    timings["zip_s"] = time.monotonic() - t
    t = time.monotonic()
    mcheck = verify_zip(zip_path, expected_name=name)
    timings["verify_zip_s"] = time.monotonic() - t
    if not mcheck.ok:
        details.append(f"manifest: {mcheck.detail}")
    verified = is_verified(
        load_ok=lc.ok,
        manifest_ok=mcheck.ok,
        parity_ok=parity_ok,
        onnx_support=info.onnx_support,
        onnx_requested=req.options.onnx,
    )
    parity_summary = None
    if parity_report:
        gating = [g for g in parity_report["graphs"] if g["gating"]]
        worst = max(gating, key=lambda g: g["max_abs_diff"] / g["atol"])
        parity_summary = {
            "max_abs_diff": worst["max_abs_diff"],
            "atol": worst["atol"],
            "rtol": worst["rtol"],
            "n_samples": parity_report["n_samples"],
        }
    verification = Verification(
        load_ok=lc.ok,
        parity_ok=parity_ok,
        manifest_ok=mcheck.ok,
        checked_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        parity=parity_summary,
        details="; ".join(details) or None,
        lelab_compatible=lelab_ok,
    )
    timings["total_s"] = time.monotonic() - t_all
    return BundleResult(
        bundle_name=name,
        bundle_dir=bundle_dir,
        zip_path=zip_path,
        zip_sha256=zip_sha,
        zip_size=zip_path.stat().st_size,
        manifest=manifest,
        onnx_status=onnx_status,
        onnx_detail=onnx_detail,
        verification=verification,
        verified=verified,
        eval_metrics=eval_metrics,
        parity_report=parity_report,
        timings=timings,
    )
