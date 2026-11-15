# syntax=docker/dockerfile:1.7
# Hibiscus web image = reverse proxy (Caddy) + the SPA static build (frontend/, A6).
# Build context: the repository root.
#   docker build -f deploy/docker/web.Dockerfile -t hibiscus/web:dev .
# The SPA is built with pnpm (docs/CONTRIBUTING.md §2) and served by Caddy from /srv; there is no
# separate web server container. Caddy runs as an unprivileged user on :8080 (public entrypoint,
# published only as 127.0.0.1:18000 by compose) and :8081 (container healthcheck only).

ARG NODE_IMAGE=node:22.12-bookworm@sha256:0e910f435308c36ea60b4cfd7b80208044d77a074d16b768a81901ce938a62dc
ARG CADDY_IMAGE=caddy:2.11.9-alpine@sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0

# ---------------------------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS spa
# pnpm is installed with npm instead of corepack: the corepack bundled with Node 22.12 fails
# signature verification against the rotated npm registry keys. Keep in sync with
# frontend/package.json "packageManager" (A6).
ARG PNPM_VERSION=9.15.0
ENV PNPM_HOME=/pnpm \
    CI=true \
    COREPACK_ENABLE_STRICT=0
ENV PATH=$PNPM_HOME:$PATH
RUN npm install -g --no-fund --no-audit "pnpm@${PNPM_VERSION}"
WORKDIR /src/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile
COPY api/ /src/api/
COPY frontend/ ./
RUN pnpm build \
 && test -f dist/index.html

# ---------------------------------------------------------------------------------------------
FROM ${CADDY_IMAGE} AS runtime
ARG HIBISCUS_VERSION=0.0.0-dev
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="hibiscus-web" \
      org.opencontainers.image.version="${HIBISCUS_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.licenses="LicenseRef-Proprietary"
RUN addgroup -S -g 10002 caddy-web \
 && adduser -S -D -H -u 10002 -G caddy-web caddy-web \
 && mkdir -p /data /config \
 && chown -R 10002:10002 /data /config
COPY deploy/caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=spa /src/frontend/dist/ /srv/
RUN caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
USER 10002:10002
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8081/livez"]
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
