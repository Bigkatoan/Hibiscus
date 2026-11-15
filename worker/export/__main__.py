"""Manual bundle build: ``python -m export --pretrained-dir ... --dataset-root ... --work-dir ...``.

Used for local runs and smoke tests; the worker calls :func:`export.bundle.build_bundle` directly.
IDs not given on the command line are random UUIDs (fine for local runs only).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

from export.bundle import build_bundle
from export.types import BundleRequest, DatasetInfo, ExportOptions, RunInfo, TrainingInfo


def _episodes(text: str) -> list[int]:
    return [int(x) for x in text.split(",") if x.strip()] if text else []


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m export", description="Build a Hibiscus model bundle")
    p.add_argument("--pretrained-dir", type=Path, required=True)
    p.add_argument("--dataset-root", type=Path, required=True)
    p.add_argument("--repo-id", required=True)
    p.add_argument("--dataset-name", required=True)
    p.add_argument("--work-dir", type=Path, required=True)
    p.add_argument("--step", type=int, required=True)
    p.add_argument("--run-number", type=int, default=1)
    p.add_argument("--run-name", default="manual")
    p.add_argument("--heldout", type=_episodes, default=[], help="comma-separated episode indices")
    p.add_argument("--total-episodes", type=int, default=0)
    p.add_argument("--seed", type=int, default=1000)
    p.add_argument("--total-steps", type=int, default=0)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--gpu-name", default="unknown")
    p.add_argument("--train-log", type=Path, action="append", default=[])
    p.add_argument("--no-onnx", action="store_true")
    p.add_argument("--fp16", action="store_true")
    p.add_argument("--no-eval", action="store_true")
    p.add_argument("--model-name")
    p.add_argument("--eval-device", default="cpu")
    p.add_argument("--load-check-python")
    p.add_argument("--parity-samples", type=int, default=32)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    heldout = sorted(args.heldout)
    train = [e for e in range(args.total_episodes) if e not in set(heldout)]
    req = BundleRequest(
        model_id=str(uuid.uuid4()),
        run=RunInfo(
            id=str(uuid.uuid4()), number=args.run_number, name=args.run_name, workspace_id=str(uuid.uuid4())
        ),
        dataset=DatasetInfo(
            dataset_id=str(uuid.uuid4()),
            version_id=str(uuid.uuid4()),
            version=1,
            name=args.dataset_name,
            content_hash="0" * 64,
            repo_id=args.repo_id,
            root=args.dataset_root,
        ),
        training=TrainingInfo(
            seed=args.seed,
            total_steps=args.total_steps or args.step,
            batch_size=args.batch_size,
            mixed_precision="no",
            gpu_name=args.gpu_name,
            heldout_episodes=heldout,
            train_episodes=train,
            gpu_seconds=0.0,
        ),
        pretrained_dir=args.pretrained_dir,
        checkpoint_step=args.step,
        work_dir=args.work_dir,
        options=ExportOptions(
            onnx=not args.no_onnx, onnx_fp16=args.fp16, eval=not args.no_eval, model_name=args.model_name
        ),
        train_logs=list(args.train_log),
        eval_device=args.eval_device,
        load_check_python=args.load_check_python,
        parity_samples=args.parity_samples,
    )
    res = build_bundle(req)
    print(
        json.dumps(
            {
                "bundle_name": res.bundle_name,
                "zip": str(res.zip_path),
                "zip_sha256": res.zip_sha256,
                "zip_size": res.zip_size,
                "verified": res.verified,
                "onnx_status": res.onnx_status,
                "onnx_detail": res.onnx_detail,
                "verification": res.verification.to_json(),
                "eval_overall": (res.eval_metrics or {}).get("overall"),
                "parity": res.parity_report,
                "timings": res.timings,
            },
            indent=2,
        )
    )
    return 0 if res.verified else 2


if __name__ == "__main__":
    sys.exit(main())
