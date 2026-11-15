"""Loading runs with tenancy/RBAC checks (D13: invisible => 404)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, ProblemError
from app.db.models import Run
from app.runs.deps import Principal, require_scope, role_at_least, workspace_role


async def load_run(
    db: AsyncSession, principal: Principal, run_id: uuid.UUID, scope: str | None
) -> tuple[Run, str]:
    run = await db.get(Run, run_id)
    if run is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "run not found")
    role = workspace_role(principal, run.workspace_id)
    require_scope(principal, scope)
    return run, role


async def load_run_for_update(db: AsyncSession, principal: Principal, run_id: uuid.UUID) -> tuple[Run, str]:
    run = await db.get(Run, run_id, with_for_update=True)
    if run is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "run not found")
    role = workspace_role(principal, run.workspace_id)
    require_scope(principal, "runs:write")
    require_can_mutate(run, principal, role)
    return run, role


def require_can_mutate(run: Run, principal: Principal, role: str) -> None:
    if not role_at_least(role, "member"):
        raise ProblemError(403, ErrorCode.FORBIDDEN, "viewers cannot change runs")
    if run.created_by != principal.user_id and not role_at_least(role, "admin"):
        raise ProblemError(403, ErrorCode.FORBIDDEN, "members can only change their own runs")
