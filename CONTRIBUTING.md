# Contributing to Hibiscus

Thank you for helping Hibiscus grow! 🌺 Bug reports, translations, pixel art, docs and code are all
welcome. This guide gets you from a fresh clone to a merged pull request.

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). Security issues go
through [SECURITY.md](SECURITY.md), never through public issues.

## Ways to contribute

* **Report a bug** or **suggest a feature** with the [issue forms](https://github.com/Bigkatoan/Hibiscus/issues/new/choose).
* **Ask a question** in [Discussions](https://github.com/Bigkatoan/Hibiscus/discussions).
* **Translate**: UI strings live in `frontend/src/i18n/{vi,en}`; user docs in `docs/user-guide/{vi,en}`.
  Vietnamese is the primary language and every key must exist in both.
* **Pixel art**: sprites, the mascot and icons come from the Hibiscus design system and are synced
  into `frontend/` (never edit `frontend/public/pixel`, `frontend/public/icons` or
  `frontend/src/hibiscus`); brand images are recomposed with `tools/brand.py`. Read the
  [style mapping](docs/ux/pixel-style.md) first and open an issue to propose new art.
* **Code**: look for issues labelled `good first issue` or `help wanted`, and comment before starting
  a large change so we can agree on the approach.

## Repository layout

| Path | What | Stack |
|---|---|---|
| `api/` | OpenAPI 3.1 contract, policy and bundle JSON Schemas | source of truth for clients |
| `backend/` | FastAPI API | Python 3.12, uv, SQLAlchemy, Postgres |
| `worker/` | validate / train / eval / export jobs | Python 3.12, uv, LeRobot 0.7.1 |
| `cli/` | `hibiscus` command-line client | Python ≥ 3.10, uv, typer |
| `frontend/` | web UI | React, TypeScript, Vite, Tailwind, pnpm |
| `deploy/` | Docker Compose stack, images, observability, backups | Docker, Caddy |
| `docs/` | user guide, runbooks, specs, ADRs, UX | mkdocs-material |
| `tests/e2e/` | end-to-end golden journey | pytest, Playwright |

## Development setup

Prerequisites: [uv](https://docs.astral.sh/uv/) ≥ 0.13, Python 3.12, Docker (integration tests use
[testcontainers](https://testcontainers.com/) for Postgres, Redis and MinIO), Node 22 + pnpm 9 for the
frontend (or run Node tooling in a container, see `deploy/scripts/node-run.sh`).

```bash
git clone https://github.com/Bigkatoan/Hibiscus.git && cd Hibiscus
make pre-commit-install          # git hooks: ruff, mypy, prettier, eslint, gitleaks, ...
make dev-up                      # dev stack on 127.0.0.1:18100-18106 (no GPU workers)
make help                        # every other target
```

> If your shell exports ROS or other paths in `PYTHONPATH`, run Python tooling with
> `env -u PYTHONPATH uv run ...` (the Makefile already does).

## Checks you should run

Each Python project (`backend/`, `worker/`, `cli/`, `deploy/`) is an independent uv project:

```bash
cd backend                       # or worker / cli / deploy
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app         # worker: `.`   cli: `hibiscus`   deploy: `scripts tests cloudflare/edge`
uv run pytest                    # GPU and slow tests are skipped by default
uv run pytest -m gpu             # only on a machine with a CUDA GPU
```

Frontend:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm lint && pnpm typecheck && pnpm exec prettier --check . && pnpm test --coverage && pnpm build
pnpm gen:api                     # after changing api/openapi.yaml
```

Everything at once, the same way CI does it: `make ci`. Docs: `uv run --with-requirements
docs/requirements.txt mkdocs serve`.

## Ground rules

* **Contract first.** API changes start in `api/openapi.yaml`; the TypeScript and Python clients are
  generated (`frontend/src/api/generated/`, `cli/hibiscus/_generated/`) and must never be hand-edited.
* **LeRobot stays unmodified.** Training runs the upstream `lerobot-train` pinned to 0.7.1; adapt to
  LeRobot with configuration and file formats, not patches.
* **Typed and tested.** `mypy --strict` and TypeScript `strict` everywhere. New behaviour comes with
  tests; integration tests use real services through testcontainers rather than mocks.
* **Secure by default.** No secrets in code, tests or compose files; validate every external input with
  pydantic; never log tokens, passwords or TOTP secrets; no `shell=True`.
* **Bilingual UI.** No hard-coded user-facing strings: add i18n keys to both `vi` and `en`.
* **Accessible.** Keep WCAG 2.1 AA contrast (the theme tests enforce it) and keyboard navigation.

## Commits and pull requests

* Use [Conventional Commits](https://www.conventionalcommits.org/):
  `feat(train): resume from the last checkpoint`, `fix(fe): ...`, `docs: ...`. Common scopes:
  `auth`, `data`, `train`, `export`, `fe`, `cli`, `deploy`, `docs`, `brand`.
* One logical change per PR; keep PRs small enough to review in one sitting.
* Fill in the PR template, link the issue (`Closes #123`) and attach screenshots for UI changes (day
  and night themes).
* CI must be green. A maintainer reviews within a few days; squash-merge is the default.
* Add a line under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md) for user-visible changes.

## License of contributions

Hibiscus is licensed under the [GNU AGPL v3.0](LICENSE). By submitting a contribution you agree that
it is licensed under the same terms (inbound = outbound) and that you have the right to submit it.

The artwork and brand assets (pixel art, the mascot Hibi, the hibiscus logo, icons, brand images and
favicons) are **not** under the AGPL; they are covered by [ASSETS-LICENSE](ASSETS-LICENSE).
