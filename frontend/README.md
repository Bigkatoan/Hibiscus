# frontend/ (owner: A6 FE; `src/i18n/` copy owned by A7 CX)

React 18 + TypeScript (strict) + Vite + Tailwind + shadcn/ui SPA (ADR-0007). Output: static files in
`dist/` (served by the reverse proxy, same origin as `/api/v1`).

## Commands (the GPU host has no Node: everything runs in `node:22.12-bookworm` via Docker)

```bash
frontend/scripts/node.sh pnpm install --frozen-lockfile
frontend/scripts/node.sh pnpm gen:api        # regenerate src/api/generated/schema.d.ts from ../api/openapi.yaml
frontend/scripts/node.sh pnpm check:api      # CI: fails if the generated client is stale
frontend/scripts/node.sh pnpm typecheck      # tsc --noEmit (strict, noUncheckedIndexedAccess, exactOptionalPropertyTypes)
frontend/scripts/node.sh pnpm lint           # eslint strict-type-checked + react-hooks + jsx-a11y, 0 warnings
frontend/scripts/node.sh pnpm format:check   # prettier
frontend/scripts/node.sh pnpm test           # vitest + Testing Library + MSW
frontend/scripts/node.sh pnpm coverage       # line threshold 70 %
frontend/scripts/node.sh pnpm build          # -> dist/
frontend/scripts/node.sh pnpm build:mock     # -> dist-mock/ (MSW browser mock mode, never deployed)
frontend/scripts/node.sh pnpm preview:mock   # serves dist-mock on 127.0.0.1:18102
```

Pixel UI (docs/ux/pixel-style.md): the Hibiscus design system is synced with
`~/hibiscus-assets/tools/sync.sh frontend --favicon` into `public/pixel`, `public/icons`,
`public/fonts` and `src/hibiscus/` (never hand-edited; version in `src/hibiscus/VERSION`). App tokens
in `src/lib/pixelTheme.ts` + `src/index.css`, mascot wrapper `src/components/Mascot.tsx`, moods in
`src/lib/hibi.ts`. Real-browser screenshots + axe: `scripts/pixel_screenshots.py` (Playwright in
Docker, see its docstring) -> `docs/ux/screenshots/pixel/`.

`dev` (127.0.0.1:18100) proxies `/api` to `HIBISCUS_DEV_API` (default `http://localhost:8080`, the
compose dev profile). Never point it at :8000 / :18000.

## Layout

| Path                                | What                                                                                                                  |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `src/api/generated/`                | `openapi-typescript` output — never hand-edit                                                                         |
| `src/api/client.ts`                 | `openapi-fetch` client + CSRF header, single-flight `/auth/refresh` on 401 `token_expired`, problem+json → `ApiError` |
| `src/api/sse.ts`                    | EventSource wrapper: `after_seq` resume, 45 s heartbeat watchdog, refresh + backoff on HTTP failure                   |
| `src/api/hooks/`                    | TanStack Query hooks per domain (one per operationId)                                                                 |
| `src/features/upload/`              | chunked resumable uploader; SHA-256 per part + whole file in a Web Worker (`hash-wasm`)                               |
| `src/features/training/`            | 4-step wizard; form rendered from the policy/train JSON Schemas (`x-hibiscus-*`)                                      |
| `src/features/runs/`                | runs list, live run detail (SSE), logs, telemetry, compare                                                            |
| `src/i18n/{en,vi}/translation.json` | copy (A7). UI uses keys only; `src/lib/i18n.test.ts` enforces completeness                                            |
| `src/test/`                         | MSW mock server typed by `openapi-msw`, fixtures validated against `api/openapi.yaml`                                 |

## SPA routes that the API must link to (emails / notifications)

`/invite?token=…` (also `/invite/:token`), `/reset-password?token=…`, `/verify-email?token=…`
(`#token=` also accepted). Workspace pages live under `/w/:slug/…`.
