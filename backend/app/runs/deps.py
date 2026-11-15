"""Request dependencies for the runs/models domain.

``Principal`` / ``get_db`` / ``current_principal`` are A2's (``app.core.deps``: cookie session +
CSRF or PAT). This module adds the run-domain authorization rules on top of them:

* PAT scopes (``runs:write ⇒ runs:read``; core already expands implications on PATs).
* Tenancy (CONTRACT_NOTES D13, same as ``app.core.deps.ensure_role``): a PAT naming another
  workspace on a list/create endpoint => 403 ``forbidden`` (the token's own workspace is known to
  the caller); a non-member naming a workspace, or any item access outside the caller's
  workspaces => 404 ``not_found`` (no existence oracle).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ROLE_RANK as _CORE_ROLE_RANK
from app.core.deps import Principal, current_principal, get_db
from app.core.errors import ErrorCode, ProblemError

__all__ = [
    "DB",
    "CurrentPrincipal",
    "Principal",
    "current_principal",
    "forbid_pat",
    "get_db",
    "has_scope",
    "require_scope",
    "role_at_least",
    "workspace_role",
]

ROLE_RANK: dict[str, int] = {str(k): v for k, v in _CORE_ROLE_RANK.items()}

DB = Annotated[AsyncSession, Depends(get_db)]
CurrentPrincipal = Annotated[Principal, Depends(current_principal)]

SCOPE_IMPLIES = {"datasets:write": {"datasets:read"}, "runs:write": {"runs:read"}}


def has_scope(p: Principal, scope: str | None) -> bool:
    if p.auth_method != "pat" or scope is None:
        return True
    granted = set(p.token_scopes)
    for s in list(granted):
        granted |= SCOPE_IMPLIES.get(s, set())
    return scope in granted


def require_scope(p: Principal, scope: str | None) -> None:
    if not has_scope(p, scope):
        raise ProblemError(
            403, ErrorCode.INSUFFICIENT_SCOPE, f"token lacks scope {scope}", params={"scope": scope}
        )


def forbid_pat(p: Principal) -> None:
    """Operations whose security list has only cookieAuth (e.g. model delete, push-hub)."""
    if p.auth_method == "pat":
        raise ProblemError(
            403, ErrorCode.INSUFFICIENT_SCOPE, "personal access tokens cannot call this operation"
        )


def workspace_role(p: Principal, workspace_id: uuid.UUID, *, for_list: bool = False) -> str:
    """Role of the caller in ``workspace_id`` (see module docstring for the tenancy rules)."""
    if p.auth_method == "pat" and p.token_workspace_id != workspace_id:
        if for_list:
            raise ProblemError(403, ErrorCode.FORBIDDEN, "token is bound to another workspace")
        raise ProblemError(404, ErrorCode.NOT_FOUND, "Not found")
    role = p.workspace_ids_roles.get(workspace_id)
    if role is None:
        # list/create and item access alike: a non-member must not learn that the workspace exists
        raise ProblemError(404, ErrorCode.NOT_FOUND, "Not found")
    return str(role)


def role_at_least(role: str, minimum: str) -> bool:
    return ROLE_RANK.get(role, 0) >= ROLE_RANK[minimum]
