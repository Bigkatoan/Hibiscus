# ADR-0009: Workspaces own data; GPUs are shared by fair-share

- **Status:** Accepted (2026-11-15)
- **Deciders:** A1 (Solution Architect), confirmed by owner (PLAN §10.2)
- **Source:** PLAN.md §2, ADR-9; §3.1, §3.3

## Context

The owner and a team share two GPUs and need to share datasets and models. Per-user ownership makes
sharing awkward; first-come-first-served scheduling lets one user monopolize the GPUs with long runs.

## Decision

- **Workspace** is the tenancy unit. Datasets, dataset versions, runs, models, PATs and quotas belong
  to a workspace. A user may belong to several workspaces.
- Roles per workspace (`workspace_members.role`):
  - `owner` — everything incl. delete workspace, transfer ownership, billing-free quotas.
  - `admin` — manage members/invites, quotas, all workspace data.
  - `member` — create datasets/runs, manage own runs, read everything in the workspace.
  - `viewer` — read only.
- Platform-level flag `users.is_platform_admin` (GPU nodes, global quotas, user management). It does
  not grant workspace data access implicitly; admin actions are audited.
- 2FA mandatory for `owner`, `admin` and platform admins (ADR-0006).
- Invites by email: link valid **72h**, single use, role fixed in the invite.
- **Fair-share scheduling** (ADR-0002): among claimable queued runs, order by `priority` (desc; values > 0
  settable only by workspace admins), then the run whose **owner** has the lowest **decayed
  GPU-seconds used in the trailing 7 days**, then oldest `queued_at` (exact SQL:
  docs/spec/run-lifecycle.md §7.1). Usage is accumulated from actual run wall-time on GPU, with exponential decay
  (configurable half-life, default 24h) within the 7-day window.
- Quotas per user and per workspace: max concurrent runs, GPU-hours per period, storage bytes.
- All API routes for tenant data are scoped: `/api/v1/workspaces/{workspace_id}/...` or include the
  workspace in the resource; authorization checks membership + role on every request.

## Consequences

### Positive
- Natural sharing of datasets/models within a team; clear permission model.
- Fair GPU access without manual coordination; priority still available for urgent runs.

### Negative
- Every query must be workspace-scoped; a missing filter is a cross-tenant data leak.
- Fair-share is per user, not per workspace; a user in several workspaces shares one budget.

### Follow-ups agents must honor
- A2: `app/workspaces` owns membership, invites and role checks, exposing `require_role(...)`
  dependencies; tests cover each role × endpoint class (matrix test).
- All agents: repository functions take `workspace_id` explicitly; no unscoped tenant queries.
  A11 reviews for IDOR; A10 includes cross-workspace access tests (expect 404, not 403).
- A4: fair-share ordering implemented in SQL in one place, unit-tested with synthetic usage data.
- A6: workspace switcher; role-aware UI (hide, but server still enforces).

## Rejected alternatives

- **Per-user ownership with explicit sharing:** cumbersome sharing of datasets/models in a team.
- **FIFO queue:** allows monopolization of two scarce GPUs.
- **Multi-org/billing:** out of scope for v1 (PLAN §1).

## Related

- ADR-0002 (queue), ADR-0006 (auth/2FA)
- `backend/app/db/models.py` (`workspaces`, `workspace_members`, `quotas`), `docs/spec/run-lifecycle.md`
