"""Run archive extraction in a resource-limited child process ("sandbox").

The child is a fresh interpreter (``python -I -m validate.sandbox``) with an empty environment,
started in a new session, that applies ``setrlimit`` before touching the archive:

* ``RLIMIT_AS``    - address space (default 2 GiB): a decompressor bug cannot eat the host RAM;
* ``RLIMIT_FSIZE`` - largest file it may write (per-file limit + 1 MiB);
* ``RLIMIT_CPU``   - CPU seconds;
* ``RLIMIT_NOFILE``/``RLIMIT_NPROC`` - no fd or fork storms; ``RLIMIT_CORE`` = 0.

It writes the ``UnpackResult`` JSON to stdout. The worker container itself adds the outer layer
(non-root user, read-only root FS, no published ports; A8). Archive bytes are never interpreted by
the parent process.
"""

from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
from pathlib import Path

from validate.archive import UnpackLimits, UnpackProblem, UnpackResult, extract_archive

DEFAULT_MEMORY_BYTES = 2 * 1024**3
DEFAULT_CPU_SECONDS = 3600


def _apply_limits(limits: UnpackLimits, memory_bytes: int, cpu_seconds: int) -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    fsize = limits.max_file_bytes + 1024 * 1024
    resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    os.umask(0o022)


def unpack_sandboxed(
    archive_path: Path,
    dest: Path,
    limits: UnpackLimits,
    *,
    memory_bytes: int = DEFAULT_MEMORY_BYTES,
    cpu_seconds: int = DEFAULT_CPU_SECONDS,
    timeout_s: float | None = None,
) -> UnpackResult:
    """Extract in a child process; returns the child's result (or an ``archive_corrupt`` problem)."""
    dest.mkdir(parents=True, exist_ok=True)
    args = {
        "archive": str(archive_path.resolve()),
        "dest": str(dest.resolve()),
        "limits": limits.to_json(),
        "memory_bytes": memory_bytes,
        "cpu_seconds": cpu_seconds,
    }
    worker_root = str(Path(__file__).resolve().parent.parent)
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8", "PYTHONPATH": worker_root}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "validate.sandbox"],
            input=json.dumps(args).encode(),
            capture_output=True,
            env=env,
            cwd=str(dest.resolve().parent),
            timeout=timeout_s or cpu_seconds + 60,
            start_new_session=True,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return UnpackResult(
            ok=False,
            problem=UnpackProblem("archive_bomb", "Unpacking timed out", params={"reason": "timeout"}),
        )
    out = proc.stdout.decode(errors="replace").strip().splitlines()
    if proc.returncode == 0 and out:
        try:
            return UnpackResult.from_json(json.loads(out[-1]))
        except (ValueError, KeyError, TypeError):
            pass
    # Killed by a limit (SIGXFSZ / SIGXCPU / MemoryError) or crashed.
    reason = f"child_exit_{proc.returncode}"
    code = "archive_bomb" if proc.returncode in (-25, -24, 137, -9) else "archive_corrupt"
    tail = proc.stderr.decode(errors="replace")[-300:]
    if "MemoryError" in tail:
        code = "archive_bomb"
        reason = "memory_limit"
    return UnpackResult(
        ok=False,
        problem=UnpackProblem(code, "Unpacking was stopped by a sandbox limit", params={"reason": reason}),
    )


def _child_main() -> int:
    args = json.loads(sys.stdin.read())
    limits = UnpackLimits.from_json(args["limits"])
    _apply_limits(limits, int(args["memory_bytes"]), int(args["cpu_seconds"]))
    result = extract_archive(Path(args["archive"]), Path(args["dest"]), limits)
    sys.stdout.write(json.dumps(result.to_json()) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(_child_main())
