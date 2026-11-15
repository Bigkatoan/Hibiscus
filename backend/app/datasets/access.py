"""Authorization rules for datasets/uploads (OpenAPI conventions, CONTRACT_NOTES D6/D8/D13).

* Workspace role: viewer < member < admin < owner. Read = viewer+, write = member+.
* PAT scopes: ``datasets:write`` implies ``datasets:read``. Missing scope -> 403 ``insufficient_scope``.
* PAT naming another workspace on list/create -> 403 ``forbidden`` (404 on item access); a user who
  is not a member -> 404 ``not_found`` everywhere (no existence oracle; same as core ``ensure_role``).
* Session-only (cookie) operations (``deleteDataset``, ``deleteDatasetVersion``) reject PATs with 403.
"""

from __future__ import annotations

import uuid
from typing import Literal

from app.core.deps import ROLE_RANK as RANK
from app.core.deps import Principal
from app.core.errors import ErrorCode, ProblemError
from app.db.models import WorkspaceRole

Scope = Literal["datasets:read", "datasets:write"]


def _has_scope(p: Principal, scope: Scope) -> bool:
    if p.auth_method != "pat":
        return True
    if scope in p.token_scopes:
        return True
    return scope == "datasets:read" and "datasets:write" in p.token_scopes


def require_scope(p: Principal, scope: Scope) -> None:
    if not _has_scope(p, scope):
        raise ProblemError(
            403, ErrorCode.INSUFFICIENT_SCOPE, f"token lacks scope {scope}", params={"scope": scope}
        )


def require_cookie(p: Principal) -> None:
    if p.auth_method != "session":
        raise ProblemError(403, ErrorCode.FORBIDDEN, "this operation is not available to access tokens")


def role_in(p: Principal, workspace_id: uuid.UUID) -> WorkspaceRole | None:
    if p.auth_method == "pat" and p.token_workspace_id != workspace_id:
        return None
    return p.workspace_ids_roles.get(workspace_id)


def require_workspace(
    p: Principal, workspace_id: uuid.UUID, min_role: WorkspaceRole, scope: Scope, *, item: bool
) -> WorkspaceRole:
    """Check access; ``item=True`` hides existence (404) for non-members."""
    if p.auth_method == "pat" and p.token_workspace_id != workspace_id:
        if item:
            raise ProblemError(404, ErrorCode.NOT_FOUND)
        raise ProblemError(403, ErrorCode.FORBIDDEN, "token is bound to another workspace")
    role = p.workspace_ids_roles.get(workspace_id)
    if role is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    require_scope(p, scope)
    if RANK[role] < RANK[min_role]:
        raise ProblemError(403, ErrorCode.FORBIDDEN, f"requires role {min_role.value}")
    return role


def at_least(role: WorkspaceRole, min_role: WorkspaceRole) -> bool:
    return RANK[role] >= RANK[min_role]
