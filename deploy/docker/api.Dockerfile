# syntax=docker/dockerfile:1.7
# Hibiscus API image (FastAPI, ADR-0001). Build context: the repository root.
#   docker build -f deploy/docker/api.Dockerfile -t hibiscus/api:dev .
# The image contains only backend/ + api/ (contract + committed policy schemas, D5): no torch,
# no LeRobot. Runs as an unprivileged user; the container listens on :8000 inside the Docker
# network only (CONTRACT_NOTES §3) — the port is never published on the host.

ARG PYTHON_IMAGE=python:3.12.16-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85

FROM ${UV_IMAGE} AS uv

# ---------------------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
# "--locked" once backend/uv.lock is committed (A2); the integrator must not ship an unlocked image.
ARG UV_SYNC_FLAGS=--locked
WORKDIR /src/backend
# Dependencies first (layer cache), then the project itself.
COPY backend/pyproject.toml backend/uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync ${UV_SYNC_FLAGS} --no-dev --no-install-project
COPY backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync ${UV_SYNC_FLAGS} --no-dev --no-editable

# ---------------------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime
ARG HIBISCUS_VERSION=0.0.0-dev
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="hibiscus-api" \
      org.opencontainers.image.version="${HIBISCUS_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.licenses="LicenseRef-Proprietary"

# tini: PID 1 that forwards SIGTERM to uvicorn so in-flight requests drain on `docker stop`.
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 hibiscus \
 && useradd --system --uid 10001 --gid hibiscus --home-dir /app --shell /usr/sbin/nologin hibiscus

COPY --from=build --chown=root:root /opt/venv /opt/venv
COPY --from=build --chown=root:root /src/backend /app
# Contract files the API serves (policy schemas, presets, bundle schemas, openapi.yaml).
COPY --chown=root:root api/ /api/

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    HIBISCUS_VERSION=${HIBISCUS_VERSION} \
    HIBISCUS_CONTRACT_DIR=/api \
    HIBISCUS_API_APP=app.main:app \
    HIBISCUS_TRUSTED_PROXY_IPS=127.0.0.1 \
    WEB_CONCURRENCY=2

WORKDIR /app
USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import sys,urllib.request;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=2).status==200 else 1)"]

ENTRYPOINT ["/usr/bin/tini", "--"]
# --proxy-headers + --forwarded-allow-ips: uvicorn takes the client address from X-Forwarded-For
# only when the TCP peer is the reverse proxy (fixed IP, see docker-compose.yml). The proxy
# overwrites X-Forwarded-For / X-Real-IP / CF-Connecting-IP with the verified client IP.
CMD ["sh", "-c", "exec uvicorn \"$HIBISCUS_API_APP\" --host 0.0.0.0 --port 8000 --no-server-header --proxy-headers --forwarded-allow-ips \"$HIBISCUS_TRUSTED_PROXY_IPS\" --timeout-graceful-shutdown 30"]
