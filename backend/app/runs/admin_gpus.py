"""``adminUpdateGpu`` (PATCH /admin/gpus/{gpu_id}) - ``app.core.deps.platform_admin`` only."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request

from app.core import audit
from app.core.audit import AuditAction
from app.core.deps import Principal, platform_admin
from app.core.errors import ErrorCode, ProblemError
from app.db.models import GpuNode, GpuNodeStatus
from app.runs.deps import DB
from app.runs.schemas import AdminGpuUpdate
from app.runs.serialize import gpu_to_dict

router = APIRouter(tags=["admin"])


@router.patch("/admin/gpus/{gpu_id}", operation_id="adminUpdateGpu")
async def admin_update_gpu(
    gpu_id: Annotated[str, Path(pattern=r"^[a-z0-9_-]{1,32}$")],
    body: AdminGpuUpdate,
    request: Request,
    db: DB,
    admin: Annotated[Principal, Depends(platform_admin)],
) -> dict[str, Any]:
    # platform_admin: browser session (no PAT), platform admin, 2FA-verified (+ CF Access when on)
    node = await db.get(GpuNode, gpu_id)
    if node is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "GPU not found")
    node.status = GpuNodeStatus(body.status)
    await audit.record(
        AuditAction.ADMIN_GPU_UPDATED,
        db=db,
        actor=admin,
        target_type="gpu_node",
        target_id=gpu_id,
        details={"status": node.status.value},
    )
    await db.commit()
    await db.refresh(node)
    return gpu_to_dict(
        node,
        offline_after_s=request.app.state.runs.settings.gpu_offline_after_s,
        run=None,
        visible=False,
        telemetry=None,
    )
