"""Process hardening for the worker processes (SEC-input-2 residual, phase-5 N3).

The training child (``lerobot-train``, estimate dry runs, load checks) runs as the same uid as
the worker. ``core.child_env`` keeps secrets out of the child's own environment, but a same-uid
process can still read the parent's exec-time environment from ``/proc/<ppid>/environ`` (and
ptrace it). Two measures close that:

* :func:`set_non_dumpable` calls ``prctl(PR_SET_DUMPABLE, 0)``. The kernel then makes the
  process's ``/proc/<pid>/*`` files root-owned and refuses ``ptrace`` attach and
  ``/proc/<pid>/environ`` / ``mem`` reads from other non-root processes, including its own
  children (the flag resets on ``execve``, so the child itself stays dumpable, and its env is the
  allow-listed one). It is the robust fix: ``/proc/<pid>/environ`` shows the exec-time env, so
  deleting variables from ``os.environ`` alone would not hide them there.
* :func:`scrub_secret_env` deletes secret-bearing variables from ``os.environ`` once the settings
  object has been built, so nothing later in the process (a library, a helper that copies
  ``os.environ``) can pick them up.

Public API: :func:`set_non_dumpable`, :func:`is_dumpable`, :func:`scrub_secret_env`,
:func:`harden_process`.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import os
import re
import sys
from collections.abc import MutableMapping

log = logging.getLogger("hibiscus.hardening")

PR_GET_DUMPABLE = 3
PR_SET_DUMPABLE = 4

#: Names removed from ``os.environ`` after settings load. Connection URLs carry passwords.
_SECRET_ENV_RE = re.compile(
    r"(SECRET|PASSWORD|PASSWD|TOKEN|CREDENTIAL|PRIVATE|_KEY$|_KEY_ID$|^AWS_|DATABASE_URL|REDIS_URL|_DSN$"
    r"|^HIBISCUS_DATA_KEY)"
)


def _libc() -> ctypes.CDLL | None:
    if not sys.platform.startswith("linux"):
        return None
    try:
        return ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
    except OSError:  # pragma: no cover - libc always exists on linux
        return None


def set_non_dumpable() -> bool:
    """``prctl(PR_SET_DUMPABLE, 0)``. Returns True when the flag is now 0; no-op off Linux."""
    libc = _libc()
    if libc is None:
        log.info("prctl(PR_SET_DUMPABLE) not available on %s; skipped", sys.platform)
        return False
    rc = libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)
    if rc != 0:
        err = ctypes.get_errno()
        log.warning("prctl(PR_SET_DUMPABLE, 0) failed: %s", os.strerror(err))
        return False
    ok = is_dumpable() is False
    log.info("process marked non-dumpable (/proc/%d/environ unreadable to same-uid processes)", os.getpid())
    return ok


def is_dumpable() -> bool | None:
    """Current dumpable flag (None when unknown / not Linux)."""
    libc = _libc()
    if libc is None:
        return None
    rc = int(libc.prctl(PR_GET_DUMPABLE, 0, 0, 0, 0))
    return None if rc < 0 else rc != 0


def is_secret_env_name(name: str) -> bool:
    return bool(_SECRET_ENV_RE.search(name.upper()))


def scrub_secret_env(environ: MutableMapping[str, str] | None = None) -> list[str]:
    """Remove secret-bearing variables from ``environ`` (default ``os.environ``); returns the names.

    Call only after every settings object has been built: the worker settings are read once at
    startup (``core.settings.get_settings`` is cached, ``validate.settings.WorkerSettings.from_env``
    is called once in ``main``) and nothing re-reads these names from the environment later.
    """
    env = os.environ if environ is None else environ
    removed = sorted(k for k in list(env) if is_secret_env_name(k))
    for k in removed:
        env.pop(k, None)
    if removed:
        log.info("removed %d secret variable(s) from the process environment", len(removed))
    return removed


def harden_process() -> None:
    """Startup hardening for a worker process whose settings are already loaded."""
    set_non_dumpable()
    scrub_secret_env()
