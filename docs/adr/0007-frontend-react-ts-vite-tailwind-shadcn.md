# ADR-0007: Frontend with React + TypeScript + Vite + Tailwind + shadcn/ui

- **Status:** Accepted (2026-11-15)
- **Deciders:** A1 (Solution Architect)
- **Source:** PLAN.md §2, ADR-7

## Context

Hibiscus needs an SPA for auth, workspace management, dataset upload/preview, a 4-step training
wizard with schema-generated forms (ADR-0005), live metrics over SSE (ADR-0010), run comparison and
model download. Requirements from PLAN §6: vi/en i18n, responsive, WCAG 2.1 AA, upload→train in
≤ 5 clicks after file selection. LeLab's frontend uses the same stack, so components may be shared
later.

## Decision

- **React 18 + TypeScript (strict) + Vite**, styled with **Tailwind CSS** and **shadcn/ui**
  (Radix primitives, copied into `frontend/src/components/ui`).
- Package manager **pnpm**. Tests: **vitest** (+ Testing Library) and **Playwright**.
- API access only through the generated client in `frontend/src/api/generated`
  (`openapi-typescript` types + `openapi-fetch`), generated from `api/openapi.yaml`. Never
  hand-edited; a thin wrapper adds CSRF header (`X-CSRF-Token` from `hb_csrf`), problem+json
  error mapping and 401→refresh retry.
- Server state via TanStack Query; SSE via `EventSource` with `Last-Event-ID` reconnection and a
  heartbeat watchdog (reconnect if no event in 45s).
- Forms: schema-driven renderer for policy configs; react-hook-form + zod for static forms.
- Charts: a canvas-based chart library suitable for thousands of points (metrics, joint plots).
- i18n: `frontend/src/i18n/{vi,en}` resource files; copy owned by A7; UI code uses keys only.
- Routing under workspace scope: `/w/:workspaceSlug/...`.
- The SPA is served as static files from the same origin as `/api/v1` (no CORS in production).

## Consequences

### Positive
- Same stack as LeLab; accessible primitives (Radix) help reach WCAG AA.
- Generated client keeps FE in lockstep with the contract; type errors surface contract drift.

### Negative
- shadcn components are vendored code we maintain.
- Strict TS settings (`noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`) slow initial work.

### Follow-ups agents must honor
- A6: owns `frontend/` except `frontend/src/i18n/` copy (A7). No hard-coded user-facing strings.
- A6: error messages are mapped from problem+json `code` to i18n keys, never from `detail` text.
- A6: vitest coverage ≥ 70%; Playwright covers every main flow; axe checks in Playwright.
- A6: never store tokens in JS-accessible storage; cookies are httpOnly by design (ADR-0006).
- Regenerate the client via the documented script whenever `api/openapi.yaml` changes; CI fails if
  the generated output differs from what is committed.

## Rejected alternatives

None considered seriously; alignment with LeLab's stack was the deciding factor (PLAN lists none).
Next.js/SSR was not needed for an authenticated SPA behind the API.

## Related

- ADR-0005 (schema forms), ADR-0006 (cookies/CSRF), ADR-0010 (SSE)
- `api/openapi.yaml`, `docs/ux/`, `docs/CONTRIBUTING.md`
