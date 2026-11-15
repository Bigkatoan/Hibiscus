"""Environment for child processes (``lerobot-train``, the estimate dry run, load checks, helpers).

SEC-input-2: the child env is built from an ALLOW-list, not by copying ``os.environ`` and
removing a few names. Whatever the deployment adds later (``HIBISCUS_DATA_KEY``,
``HIBISCUS_DATABASE_URL_SYNC``, ``*_SECRET_ACCESS_KEY``, cloud credentials, tokens, ...) never
reaches code that runs a user's model or config.

Public API: :func:`child_env`, :data:`ALLOWED_NAMES`, :data:`ALLOWED_PREFIXES`.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping

#: Exact names copied from the parent when present.
ALLOWED_NAMES = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "LANG",
        "LANGUAGE",
        "TZ",
        "TMPDIR",
        "TERM",
        "VIRTUAL_ENV",
        "LD_LIBRARY_PATH",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "TORCH_HOME",
        "MPLCONFIGDIR",
        "XDG_CACHE_HOME",
        "HF_HOME",
        "HF_HUB_OFFLINE",
        "HF_HUB_DISABLE_TELEMETRY",
        "HF_HUB_ENABLE_HF_TRANSFER",
        "HF_ENDPOINT",
        "HF_DATASETS_OFFLINE",
        "TRANSFORMERS_OFFLINE",
        "PYTHONUNBUFFERED",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONHASHSEED",
        "PYTHONIOENCODING",
        "TQDM_DISABLE",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    }
)
#: Name prefixes copied from the parent (GPU runtime and locale only).
ALLOWED_PREFIXES = ("CUDA_", "NVIDIA_", "NCCL_", "PYTORCH_", "LC_", "CUBLAS_", "CUDNN_")

#: Never passed, even when an allow-listed prefix or an explicit ``extra_prefixes`` matches.
_SECRET_RE = re.compile(r"(SECRET|PASSWORD|PASSWD|TOKEN|CREDENTIAL|PRIVATE|_KEY$|_KEY_ID$|^AWS_|^HIBISCUS_)")


def is_secret_name(name: str) -> bool:
    return bool(_SECRET_RE.search(name.upper()))


def child_env(
    *,
    base: Mapping[str, str] | None = None,
    extra_prefixes: Iterable[str] = (),
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Allow-listed copy of ``base`` (default ``os.environ``) plus ``overrides``.

    ``overrides`` is set as given (callers use it for ``HF_HOME``, ``HF_HUB_OFFLINE``,
    ``CUDA_VISIBLE_DEVICES``, ...). ``PYTHONPATH`` is never inherited (ROS pollution, and it
    would let the parent's import path leak into the child).
    """
    src = os.environ if base is None else base
    prefixes = (*ALLOWED_PREFIXES, *(p for p in extra_prefixes if p))
    env: dict[str, str] = {}
    for name, value in src.items():
        if name in ("PYTHONPATH", "AMENT_PREFIX_PATH"):
            continue
        if (name in ALLOWED_NAMES or name.startswith(prefixes)) and not is_secret_name(name):
            env[name] = value
    if overrides:
        env.update(overrides)
    env.setdefault("PATH", os.defpath)
    return env
