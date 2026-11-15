#!/usr/bin/env bash
# Build Hibiscus images from the repository root. Usage:
#   deploy/scripts/build-images.sh [api|web|worker-gpu|worker-gpu-pascal|worker-cpu|all] [--tag TAG]
# Build args for each worker variant are the single source of truth here and in
# deploy/docker-compose.yml (x-worker-build-* anchors); keep them in sync.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET="${1:-all}"
TAG="${HIBISCUS_IMAGE_TAG:-dev}"
if [[ "${2:-}" == "--tag" ]]; then TAG="${3:?--tag needs a value}"; fi
VCS_REF="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
# HIBISCUS_BUILD_NETWORK=host is needed on hosts where bridge containers have no egress/DNS
# (the GPU box at the time of writing, see docs/runbook/install.md).
COMMON=(--network "${HIBISCUS_BUILD_NETWORK:-default}"
        --build-arg "VCS_REF=${VCS_REF}" --build-arg "HIBISCUS_VERSION=${HIBISCUS_VERSION:-0.1.0}")

build_api() {
  docker build "${COMMON[@]}" -f "$ROOT/deploy/docker/api.Dockerfile" -t "hibiscus/api:${TAG}" "$ROOT"
}
build_web() {
  docker build "${COMMON[@]}" -f "$ROOT/deploy/docker/web.Dockerfile" -t "hibiscus/web:${TAG}" "$ROOT"
}
build_worker_gpu() {
  docker build "${COMMON[@]}" -f "$ROOT/deploy/docker/worker.Dockerfile" \
    --build-arg RUNTIME_BASE=nvidia/cuda:13.2.0-base-ubuntu24.04 \
    --build-arg TORCH_INDEX_URL=https://pypi.org/simple \
    --build-arg "TORCH_PACKAGES=torch==2.15.0 torchvision==0.29.2" \
    --build-arg "TORCHCODEC_PACKAGE=torchcodec==0.17.0" \
    --build-arg WORKER_VARIANT=gpu \
    -t "hibiscus/worker-gpu:${TAG}" "$ROOT"
}
build_worker_gpu_pascal() {
  docker build "${COMMON[@]}" -f "$ROOT/deploy/docker/worker.Dockerfile" \
    --build-arg RUNTIME_BASE=nvidia/cuda:12.6.3-base-ubuntu24.04 \
    --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu126 \
    --build-arg "TORCH_PACKAGES=torch==2.14.1 torchvision==0.29.1" \
    --build-arg "TORCHCODEC_PACKAGE=torchcodec==0.16.0" \
    --build-arg WORKER_VARIANT=gpu-pascal \
    -t "hibiscus/worker-gpu-pascal:${TAG}" "$ROOT"
}
build_worker_cpu() {
  docker build "${COMMON[@]}" -f "$ROOT/deploy/docker/worker.Dockerfile" \
    --build-arg RUNTIME_BASE=python:3.12.16-slim-trixie \
    --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu \
    --build-arg "TORCH_PACKAGES=torch==2.15.0 torchvision==0.29.1" \
    --build-arg "TORCHCODEC_PACKAGE=torchcodec==0.17.0" \
    --build-arg WORKER_VARIANT=cpu \
    -t "hibiscus/worker-cpu:${TAG}" "$ROOT"
}

case "$TARGET" in
  api) build_api ;;
  web) build_web ;;
  worker-gpu) build_worker_gpu ;;
  worker-gpu-pascal) build_worker_gpu_pascal ;;
  worker-cpu) build_worker_cpu ;;
  all) build_api; build_web; build_worker_gpu; build_worker_gpu_pascal; build_worker_cpu ;;
  *) echo "unknown target: $TARGET" >&2; exit 2 ;;
esac
