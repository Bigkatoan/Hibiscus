"""``load_ok`` check (docs/spec/bundle.md §10), run in a FRESH interpreter.

Standalone on purpose: imports only the stdlib, torch and lerobot, so the same file can be run
with the worker image's Python *and* with the LeLab venv
(``~/lelab/leLab/.venv/bin/python -I worker/export/load_check.py --policy-dir ...``).

Prints one JSON line ``{"ok": bool, ...}`` on stdout; exit code 0 iff ok.
:func:`run_load_check` is the in-process API that spawns the subprocess.

``--block-modules a,b`` hides those top-level packages from the import system before LeRobot is
imported (``importlib.util.find_spec`` returns ``None`` and ``import`` raises
``ModuleNotFoundError``). With ``export.lelab_compat.LELAB_MISSING_MODULES`` this reproduces the
LeLab venv (same LeRobot commit, no optional extras) inside the worker image (QC-ml-1).
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess  # argv list, no shell
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_THIS = Path(__file__).resolve()


@dataclass
class LoadCheckResult:
    ok: bool
    action_shape: list[int] = field(default_factory=list)
    finite: bool = False
    detail: str | None = None
    lerobot_version: str | None = None
    python: str | None = None
    seconds: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


def run_load_check(
    policy_dir: Path,
    *,
    dataset_root: Path,
    repo_id: str,
    episode: int,
    frame: int = 0,
    python: str | None = None,
    device: str = "cpu",
    timeout_s: float = 900.0,
    env: dict[str, str] | None = None,
    block_modules: tuple[str, ...] | list[str] = (),
) -> LoadCheckResult:
    """Spawn ``python -I load_check.py`` and parse its JSON verdict."""
    argv = [
        python or sys.executable,
        "-I",
        str(_THIS),
        "--policy-dir",
        str(policy_dir),
        "--dataset-root",
        str(dataset_root),
        "--repo-id",
        repo_id,
        "--episode",
        str(episode),
        "--frame",
        str(frame),
        "--device",
        device,
    ]
    if block_modules:
        argv += ["--block-modules", ",".join(block_modules)]
    if env is None:
        # SEC-input-2: allow-listed env only (lazy import: this file also runs standalone).
        from core.child_env import child_env as _allowed

        child_env = _allowed()
    else:
        child_env = dict(env)
    # ROS-style PYTHONPATH pollution must not leak into the check (CONTRIBUTING §9).
    child_env.pop("PYTHONPATH", None)
    child_env.setdefault("HF_HUB_OFFLINE", "1")
    t0 = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S603  # fixed argv, no shell
            argv, capture_output=True, text=True, timeout=timeout_s, env=child_env, check=False
        )
    except subprocess.TimeoutExpired:
        return LoadCheckResult(ok=False, detail=f"load check timed out after {timeout_s:.0f}s")
    elapsed = time.monotonic() - t0
    line = next((ln for ln in reversed(proc.stdout.strip().splitlines()) if ln.startswith("{")), None)
    if line is None:
        tail = (proc.stderr or proc.stdout)[-2000:]
        return LoadCheckResult(
            ok=False, detail=f"load check produced no verdict (rc={proc.returncode}): {tail}"
        )
    data: dict[str, Any] = json.loads(line)
    return LoadCheckResult(
        ok=bool(data.get("ok")) and proc.returncode == 0,
        action_shape=list(data.get("action_shape") or []),
        finite=bool(data.get("finite")),
        detail=data.get("error"),
        lerobot_version=data.get("lerobot_version"),
        python=data.get("python"),
        seconds=elapsed,
        raw=data,
    )


def run_load_checks(
    policy_dir: Path,
    *,
    dataset_root: Path,
    repo_id: str,
    episode: int,
    lelab_python: str | None = None,
) -> tuple[LoadCheckResult, LoadCheckResult]:
    """QC-ml-1: ``(load, lelab)``.

    ``lelab`` = the check in the LeLab venv (``lelab_python``, or this interpreter with
    ``LELAB_MISSING_MODULES`` hidden). ``load`` = LeRobot 0.7.1 with every extra installed (the
    worker env); it is only run separately when the LeLab check fails.
    """
    from export.lelab_compat import LELAB_MISSING_MODULES

    lelab = run_load_check(
        policy_dir,
        dataset_root=dataset_root,
        repo_id=repo_id,
        episode=episode,
        python=lelab_python,
        block_modules=() if lelab_python else LELAB_MISSING_MODULES,
    )
    if lelab.ok:
        return lelab, lelab
    load = run_load_check(policy_dir, dataset_root=dataset_root, repo_id=repo_id, episode=episode)
    return load, lelab


# --------------------------------------------------------------------------------------------
# Child process
# --------------------------------------------------------------------------------------------
def block_imports(names: set[str]) -> None:
    """Make the top-level packages ``names`` look uninstalled to this interpreter."""
    from importlib.machinery import PathFinder

    original = PathFinder.find_spec

    def find_spec(cls: Any, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname.partition(".")[0] in names:
            return None
        return original(fullname, path, target)

    PathFinder.find_spec = classmethod(find_spec)  # type: ignore[method-assign,assignment]
    for mod in list(sys.modules):
        if mod.partition(".")[0] in names:
            del sys.modules[mod]


def _check(args: argparse.Namespace) -> dict[str, Any]:  # pragma: no cover - runs in a subprocess
    import torch
    from lerobot import __version__ as lerobot_version
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.policies.factory import get_policy_class, make_pre_post_processors

    policy_dir = Path(args.policy_dir)
    ptype = json.loads((policy_dir / "config.json").read_text())["type"]
    cls = get_policy_class(ptype)
    cfg = PreTrainedConfig.from_pretrained(str(policy_dir))
    cfg.device = args.device
    policy = cls.from_pretrained(str(policy_dir), config=cfg)
    policy.eval()
    # Same loading path as lerobot-rollout / lerobot-eval (PolicyProcessorPipeline.from_pretrained
    # of policy_preprocessor.json / policy_postprocessor.json with the policy's converters).
    pre, post = make_pre_post_processors(
        cfg,
        pretrained_path=str(policy_dir),
        preprocessor_overrides={"device_processor": {"device": args.device}},
        postprocessor_overrides={"device_processor": {"device": "cpu"}},
    )
    ds = LeRobotDataset(args.repo_id, root=args.dataset_root, episodes=[args.episode])
    item = ds[min(args.frame, len(ds) - 1)]
    obs = {k: v for k, v in item.items() if k.startswith("observation.")}
    if "task" in item:
        obs["task"] = item["task"]
    policy.reset()
    with torch.inference_mode():
        batch = pre(obs)
        action = policy.select_action(batch)
        action = post(action)
    shape = [int(s) for s in action.shape]
    finite = bool(torch.isfinite(action).all().item())
    adim = int(cfg.output_features["action"].shape[0])
    ok = finite and shape == [1, adim]
    return {
        "ok": ok,
        "policy_type": ptype,
        "action_shape": shape,
        "finite": finite,
        "first_action": [float(x) for x in action.reshape(-1).tolist()],
        "lerobot_version": lerobot_version,
        "torch_version": torch.__version__,
        "python": sys.version.split()[0],
        "error": None if ok else f"expected finite action of shape [1, {adim}], got {shape} finite={finite}",
    }


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - runs in a subprocess
    parser = argparse.ArgumentParser(description="Hibiscus bundle load check")
    parser.add_argument("--policy-dir", required=True)
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--episode", type=int, required=True)
    parser.add_argument("--frame", type=int, default=0)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--block-modules", default="")
    args = parser.parse_args(argv)
    blocked = {m for m in args.block_modules.split(",") if m}
    if blocked:
        block_imports(blocked)
    try:
        result = _check(args)
    except Exception as exc:  # report every failure as a verdict, never a traceback only
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    result["blocked_modules"] = sorted(blocked)
    for key, value in list(result.items()):
        if isinstance(value, float) and not math.isfinite(value):
            result[key] = None
    print(json.dumps(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
