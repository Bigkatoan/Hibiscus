# syntax=docker/dockerfile:1.7
# Hibiscus worker images. Build context: the repository root. One Dockerfile, three variants
# selected with build args (see deploy/docker-compose.yml, `x-worker-build-*`):
#
#   variant        RUNTIME_BASE                           TORCH_INDEX_URL                        torch
#   gpu (cuda0)    nvidia/cuda:13.2.0-base-ubuntu24.04    https://pypi.org/simple (cu132 wheels) 2.15.0  RTX 3060 sm_86
#   gpu-pascal     nvidia/cuda:12.6.3-base-ubuntu24.04    https://download.pytorch.org/whl/cu126 2.14.1  Tesla P40 sm_61
#   cpu            python:3.12.16-slim-trixie              https://download.pytorch.org/whl/cpu   2.15.0  validate/import
#
# Why two GPU variants: torch 2.15.0 is only published for CUDA 13.2/13.4, whose kernels start at
# sm_75; the P40 (Pascal, sm_61) cannot run them. The newest torch that still ships sm_61 kernels
# is 2.14.1+cu126 (lerobot 0.7.1 accepts torch>=2.7,<2.16). See CONTRACT_NOTES CR-A8-1.
# The image runs `lerobot-train` unmodified as a subprocess (ADR-0003); LeRobot is pinned 0.7.1.

ARG RUNTIME_BASE=nvidia/cuda:13.2.0-base-ubuntu24.04@sha256:36cccda4bebc3b0b1ebe1907ead8169cf144d45df890be871b36b304cf91145a
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85

FROM ${UV_IMAGE} AS uv

# ---------------------------------------------------------------------------------------------
FROM ${RUNTIME_BASE} AS runtime
ARG PYTHON_VERSION=3.12.16
ARG TORCH_INDEX_URL=https://pypi.org/simple
ARG TORCH_PACKAGES="torch==2.15.0 torchvision==0.29.2"
ARG TORCHCODEC_PACKAGE="torchcodec==0.17.0"
ARG LEROBOT_VERSION=0.7.1
# lerobot 0.7.1 is not on PyPI (the newest release there is 0.7.0). The reference LeLab venv
# installed it from this upstream commit (its dist-info direct_url.json). Pinned by commit.
ARG LEROBOT_GIT_URL=https://github.com/huggingface/lerobot.git
ARG LEROBOT_GIT_REF=fe1c54594f6ba275fccf210b9f7b11f0e2324b89
ARG WORKER_VARIANT=gpu
ARG HIBISCUS_VERSION=0.0.0-dev
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="hibiscus-worker-${WORKER_VARIANT}" \
      org.opencontainers.image.version="${HIBISCUS_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.licenses="LicenseRef-Proprietary" \
      ai.hibiscus.lerobot.version="${LEROBOT_VERSION}"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
# ffmpeg: AV1/H.264 decode (torchcodec, pyav) and H.264 preview encode (CONTRACT_NOTES §4.5).
# libarchive: RAR5/zip/tar unpack in the sandboxed unpacker (worker/validate, PLAN §1).
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get install -y --no-install-recommends \
      ca-certificates git tini ffmpeg libarchive13t64 libgl1 libglib2.0-0 procps \
 && rm -rf /var/lib/apt/lists/* \
 && (getent passwd 1000 >/dev/null && userdel --remove "$(getent passwd 1000 | cut -d: -f1)" || true) \
 && groupadd --system --gid 10001 hibiscus \
 && useradd --system --uid 10001 --gid hibiscus --home-dir /home/hibiscus --create-home --shell /usr/sbin/nologin hibiscus

COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv python install "${PYTHON_VERSION}" \
 && uv venv --python "${PYTHON_VERSION}" /opt/venv \
 && rm -rf /opt/python/cpython-*/lib/python3.12/site-packages/pip \
           /opt/python/cpython-*/lib/python3.12/site-packages/pip-*.dist-info \
           /opt/python/cpython-*/lib/python3.12/ensurepip
# ^ the interpreter's bundled pip is never used (uv installs everything) and its vendored SBOM
#   reports setuptools 70.3.0 (CVE-2025-47273) to trivy.

# 1) torch stack from the variant-specific index (exact versions, see table above).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /opt/venv/bin/python --index-url "${TORCH_INDEX_URL}" ${TORCH_PACKAGES}

# 2) everything else from PyPI, constrained so the torch stack above is never replaced. The
#    direct URL requirement for the pinned upstream commit satisfies worker/pyproject.toml's
#    `lerobot[training]==0.7.1` (0.7.1 is not published on PyPI). Do not use --override here:
#    it drops lerobot's self-referencing extras (dataset, av-dep, accelerate-dep).
COPY worker/pyproject.toml /src/worker/pyproject.toml
COPY deploy/docker/worker-constraints.txt /src/worker-constraints.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    /opt/venv/bin/python -c "import importlib.metadata as m; print('\n'.join(f'{p}=={m.version(p).split(\"+\")[0]}' for p in ('torch','torchvision')))" > /src/torch-pins.txt \
 && uv pip install --python /opt/venv/bin/python \
      --constraint /src/torch-pins.txt --constraint /src/worker-constraints.txt \
      "lerobot[training] @ git+${LEROBOT_GIT_URL}@${LEROBOT_GIT_REF}" ${TORCHCODEC_PACKAGE} \
      -r /src/worker/pyproject.toml \
 && LEROBOT_VERSION="${LEROBOT_VERSION}" /opt/venv/bin/python - <<'PY'
import importlib.metadata as m
import os
assert m.version("lerobot") == os.environ["LEROBOT_VERSION"], m.version("lerobot")
print({p: m.version(p) for p in ("lerobot", "torch", "torchvision", "torchcodec", "av", "accelerate")})
PY

# Worker packages (train, validate, export, eval, core; CONTRACT_NOTES D14). Imported from /app.
COPY --chown=root:root worker/ /app/
COPY --chown=root:root api/ /api/

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CUDA_DEVICE_ORDER=PCI_BUS_ID \
    HF_HOME=/cache/hf \
    HF_HUB_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TORCH_HOME=/cache/torch \
    MPLCONFIGDIR=/tmp/matplotlib \
    HIBISCUS_WORKER_VARIANT=${WORKER_VARIANT} \
    HIBISCUS_VERSION=${HIBISCUS_VERSION} \
    HIBISCUS_CONTRACT_DIR=/api \
    HIBISCUS_WORKER_HEARTBEAT_FILE=/tmp/hibiscus-worker.alive \
    HIBISCUS_WORKER_MODULE=train

# Shared host volumes (run-lifecycle §10). Pre-created so named volumes inherit the ownership.
RUN mkdir -p /cache/datasets /cache/hf /cache/torch /scratch/runs /scratch/exports \
 && chown -R 10001:10001 /cache /scratch
VOLUME ["/cache", "/scratch"]

WORKDIR /app
USER 10001:10001

# Liveness (QC-e2e-08): see deploy/docker/worker-healthcheck.sh. A fresh heartbeat file when the
# worker writes one, otherwise "python -m $HIBISCUS_WORKER_MODULE is running". The lease heartbeat
# in Postgres stays the source of truth for run ownership (ADR-0002); this only lets Docker see a
# dead or wedged process.
COPY --chown=root:root --chmod=0755 deploy/docker/worker-healthcheck.sh /usr/local/bin/hibiscus-worker-healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD ["/usr/local/bin/hibiscus-worker-healthcheck"]

ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
CMD ["sh", "-c", "exec python -m \"$HIBISCUS_WORKER_MODULE\""]
