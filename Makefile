# Hibiscus developer / operator entry points (owner: A8). `make help` lists targets.
# Host quirks (docs/runbook/install.md): ROS pollutes PYTHONPATH -> every uv call strips it; there
# may be no node on the host -> Node tooling runs in node:22.12 containers.

SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

ROOT        := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
DEPLOY      := $(ROOT)/deploy
UV          := env -u PYTHONPATH -u AMENT_PREFIX_PATH uv
UVRUN       := $(UV) run
PY_PROJECTS := backend worker cli deploy
NODE_IMAGE  := node:22.12-bookworm
# host network: bridge containers have no egress on the GPU box (docs/runbook/install.md)
NODE_NETWORK ?= host
NODE        := docker run --rm --network $(NODE_NETWORK) -u $$(id -u):$$(id -g) -e HOME=/tmp -e CI=true
COMPOSE     := docker compose --project-directory $(DEPLOY) -f $(DEPLOY)/docker-compose.yml
COMPOSE_DEV := docker compose -p hibiscus-dev --project-directory $(DEPLOY) -f $(DEPLOY)/docker-compose.yml -f $(DEPLOY)/compose.dev.yml
# compose builds with the daemon's BuildKit (a docker-container buildx builder may lack egress here)
export BUILDX_BUILDER ?= default

.PHONY: help
help: ## show this help
	@grep -hE '^[a-zA-Z0-9_.-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------------------------
# Production stack (deploy/docker-compose.yml, public entrypoint 127.0.0.1:18000)
# ---------------------------------------------------------------------------------------------
$(DEPLOY)/.env:
	@echo "deploy/.env missing: cp deploy/.env.example deploy/.env and fill it (deploy/scripts/gen-secrets.sh)"; exit 1

.PHONY: env secrets
env: ## create deploy/.env from the example (refuses to overwrite)
	@test ! -e $(DEPLOY)/.env || { echo "deploy/.env exists"; exit 1; }
	cp $(DEPLOY)/.env.example $(DEPLOY)/.env && chmod 600 $(DEPLOY)/.env
	@echo "now edit deploy/.env (secrets: make secrets)"
secrets: ## print freshly generated secret values (stdout only)
	@$(DEPLOY)/scripts/gen-secrets.sh

.PHONY: build build-api build-web build-workers
build: ## build all images (api, web, worker-gpu, worker-gpu-pascal, worker-cpu)
	$(DEPLOY)/scripts/build-images.sh all
build-api: ## build hibiscus/api
	$(DEPLOY)/scripts/build-images.sh api
build-web: ## build hibiscus/web (Caddy + SPA)
	$(DEPLOY)/scripts/build-images.sh web
build-workers: ## build the three worker images
	$(DEPLOY)/scripts/build-images.sh worker-cpu
	$(DEPLOY)/scripts/build-images.sh worker-gpu
	$(DEPLOY)/scripts/build-images.sh worker-gpu-pascal

.PHONY: up down restart ps logs config
up: $(DEPLOY)/.env config ## start the production stack (checks the exposure policy first)
	$(COMPOSE) up -d --wait --wait-timeout 300
down: ## stop the production stack (volumes kept)
	$(COMPOSE) down
restart: ## restart api + proxy (e.g. after editing deploy/.env)
	$(COMPOSE) up -d --force-recreate api proxy
ps: ## service status
	$(COMPOSE) ps
logs: ## follow logs (SERVICE=api to filter)
	$(COMPOSE) logs -f --tail 200 $(SERVICE)
config: ## render compose (prod + dev) and enforce the port/network policy
	$(COMPOSE) --env-file $(DEPLOY)/.env.example config -q
	$(COMPOSE_DEV) --env-file $(DEPLOY)/.env.example config -q
	$(UVRUN) --project $(DEPLOY) python $(DEPLOY)/scripts/check_compose.py --mode prod
	$(UVRUN) --project $(DEPLOY) python $(DEPLOY)/scripts/check_compose.py --mode dev

.PHONY: dev-up dev-down dev-ps
dev-up: ## start the dev stack (project hibiscus-dev, ports 18100-18106, no GPU workers)
	$(COMPOSE_DEV) up -d --wait --wait-timeout 300
dev-down: ## stop the dev stack and DELETE its volumes
	$(COMPOSE_DEV) down -v --remove-orphans
dev-ps:
	$(COMPOSE_DEV) ps

# ---------------------------------------------------------------------------------------------
# Backups (docs/runbook/backup-restore.md)
# ---------------------------------------------------------------------------------------------
.PHONY: backup-now restore-drill
backup-now: ## take a Postgres backup immediately
	$(COMPOSE) exec -T backup bash /backup/pg-backup.sh
restore-drill: ## restore DUMP=<file> into a scratch DB (hibiscus_restore_drill); live DB untouched
	@test -n "$(DUMP)" || { echo "usage: make restore-drill DUMP=deploy/backups/<file>.dump"; exit 2; }
	$(DEPLOY)/backup/restore.sh "$(DUMP)" --target-db hibiscus_restore_drill --yes

# ---------------------------------------------------------------------------------------------
# Quality gates (same as .github/workflows/ci.yml)
# ---------------------------------------------------------------------------------------------
.PHONY: lint typecheck test test-deploy test-smoke email-worker-check frontend-check audit scan ci
lint: ## ruff (all uv projects present)
	@for p in $(PY_PROJECTS); do [ -f $(ROOT)/$$p/pyproject.toml ] || continue; echo "== ruff $$p"; \
	  (cd $(ROOT)/$$p && $(UVRUN) ruff check . && $(UVRUN) ruff format --check .); done
typecheck: ## mypy --strict (all uv projects present)
	@[ ! -f $(ROOT)/backend/pyproject.toml ] || (cd $(ROOT)/backend && $(UVRUN) mypy --strict app)
	@[ ! -f $(ROOT)/worker/pyproject.toml ] || (cd $(ROOT)/worker && $(UVRUN) mypy --strict .)
	@[ ! -f $(ROOT)/cli/pyproject.toml ] || (cd $(ROOT)/cli && $(UVRUN) mypy --strict hibiscus)
	cd $(DEPLOY) && $(UVRUN) mypy --strict scripts tests cloudflare/edge
test: ## unit/integration tests of every uv project (gpu/slow excluded)
	@for p in backend worker cli; do [ -f $(ROOT)/$$p/pyproject.toml ] || continue; echo "== pytest $$p"; \
	  (cd $(ROOT)/$$p && $(UVRUN) pytest -q); done
	$(MAKE) test-deploy
test-deploy: ## deploy tooling tests (compose policy, backup/restore, exporter, configs, edge)
	cd $(DEPLOY) && $(UVRUN) pytest -q -m "not slow"
test-smoke: ## full stack smoke test with stub app (builds images; ~2 min warm)
	cd $(DEPLOY) && $(UVRUN) pytest -q -m slow tests/test_stack_smoke.py
email-worker-check: ## tsc + eslint + prettier + vitest + wrangler dry-run for the Email Worker
	$(NODE) -v $(DEPLOY)/cloudflare/email-worker:/w -w /w $(NODE_IMAGE) sh -c 'npm ci --no-fund --no-audit && npm run check'
frontend-check: ## lint/typecheck/test/build the SPA (when frontend/package.json exists)
	@[ -f $(ROOT)/frontend/package.json ] || { echo "no frontend yet"; exit 0; }
	$(NODE) -v $(ROOT):/w -w /w/frontend $(NODE_IMAGE) sh -c 'npm i -g pnpm@9.15.0 --prefix /tmp/pnpm >/dev/null && \
	  PATH=/tmp/pnpm/bin:$$PATH pnpm install --frozen-lockfile && PATH=/tmp/pnpm/bin:$$PATH pnpm lint && \
	  PATH=/tmp/pnpm/bin:$$PATH pnpm typecheck && PATH=/tmp/pnpm/bin:$$PATH pnpm coverage'
audit: ## pip-audit for each uv.lock + npm audit (high+)
	@for p in $(PY_PROJECTS); do [ -f $(ROOT)/$$p/uv.lock ] || continue; echo "== pip-audit $$p"; \
	  $(UV) export --project $(ROOT)/$$p --locked --no-hashes --no-emit-project --format requirements-txt > /tmp/hibiscus-$$p-req.txt; \
	  $(UV) tool run --python 3.12 pip-audit --strict --disable-pip --no-deps -r /tmp/hibiscus-$$p-req.txt; done
	$(NODE) -v $(DEPLOY)/cloudflare/email-worker:/w -w /w $(NODE_IMAGE) npm audit --audit-level=high
scan: ## trivy scan of built images (IMAGES="hibiscus/api:dev ..."), via docker save (no socket mount)
	@for img in $${IMAGES:-hibiscus/api:dev hibiscus/web:dev hibiscus/worker-cpu:dev}; do echo "== trivy $$img"; \
	  tmp=$$(mktemp -d); docker save -o $$tmp/img.tar $$img; \
	  docker run --rm -v $$tmp:/scan:ro -v hibiscus-trivy-cache:/root/.cache aquasec/trivy:0.76.2 image --input /scan/img.tar \
	    --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 --scanners vuln,secret; rm -rf $$tmp; done
ci: config lint typecheck test email-worker-check ## everything CI runs except image builds/scans
	$(UVRUN) --project $(DEPLOY) python $(DEPLOY)/scripts/gen_dashboards.py --check

.PHONY: pre-commit-install
pre-commit-install: ## install the git hooks (once per worktree)
	$(UV) tool run pre-commit install
