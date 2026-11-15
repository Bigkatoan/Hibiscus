"""Runs CRUD + lifecycle actions (createRun, listRuns, getRun, updateRun, cancelRun, pauseRun,
resumeRun, cloneRun, preflightRun, compareRuns, checkpoints, manifest)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.audit import AuditAction
from app.core.errors import ErrorCode, ProblemError
from app.core.pagination import decode_cursor, encode_cursor
from app.db.models import (
    Checkpoint,
    DatasetVersion,
    GpuNode,
    Job,
    JobKind,
    JobResource,
    JobStatus,
    MixedPrecision,
    Model,
    ModelStatus,
    OnnxStatus,
    Run,
    RunStatus,
)
from app.runs.access import load_run, load_run_for_update, require_can_mutate
from app.runs.catalog import POLICY_META, get_catalog
from app.runs.config import deep_merge
from app.runs.deps import DB, CurrentPrincipal, Principal, require_scope, role_at_least, workspace_role
from app.runs.errors import invalid_transition
from app.runs.events import QUEUE_CHANNEL, Outbox, append_run_event, control_channel, iso_now, transition
from app.runs.metrics import downsample_series, load_series
from app.runs.preflight import PreflightResult, effective_quota, gpu_hours_this_month, run_preflight
from app.runs.schemas import (
    ExportOptions,
    RunCloneRequest,
    RunCreate,
    RunPauseRequest,
    RunResumeRequest,
    RunUpdate,
)
from app.runs.serialize import checkpoint_to_dict, job_to_dict, model_to_dict, runs_to_dicts
from app.runs.settings import disallowed_hub_models

router = APIRouter(tags=["runs"])

IDEM_TTL_S = 24 * 3600


def _state(request: Request) -> Any:
    return request.app.state.runs


async def _audit(
    db: AsyncSession, action: AuditAction, principal: Principal, run: Run, **details: Any
) -> None:
    await audit.record(
        action,
        db=db,
        actor=principal,
        workspace_id=run.workspace_id,
        target_type="run",
        target_id=str(run.id),
        details=details,
    )


async def _publish(request: Request, outbox: Outbox, *extra: tuple[str, str]) -> None:
    redis = _state(request).redis
    await outbox.flush(redis)
    if redis is None:
        return
    for ch, msg in extra:
        try:
            await redis.publish(ch, msg)
        except Exception:  # noqa: S112 - best-effort wake-up hint
            continue


async def _one(db: AsyncSession, principal: Principal, run: Run) -> dict[str, Any]:
    roles = {run.workspace_id: principal.workspace_ids_roles.get(run.workspace_id, "viewer")}
    return (await runs_to_dicts(db, [run], principal, roles))[0]


def _require_allowed_hf_init(request: Request, run: Run) -> None:
    """SEC-input-1: a run created (before the allow-list) from a Hub repo that is not approved
    must not be started again: the worker would load the repo's processor code."""
    init = (run.config or {}).get("_init_from")
    repo = init.get("hf_repo_id") if isinstance(init, dict) else None
    if repo and not _state(request).settings.hf_repo_allowed(str(repo)):
        raise ProblemError(
            403,
            ErrorCode.FORBIDDEN,
            f"{repo} is not on the platform's allow-list of Hugging Face repos",
            params={"hf_repo_id": str(repo), "reason": "hf_repo_not_allowed"},
        )
    bad = disallowed_hub_models(
        (run.config or {}).get("policy") or {}, _state(request).settings.vlm_model_allowlist
    )
    if bad:
        fname, value = next(iter(bad.items()))
        raise ProblemError(
            403,
            ErrorCode.FORBIDDEN,
            f"policy.{fname}={value!r} is not on the platform's allow-list of Hugging Face models",
            params={"field": f"policy.{fname}", "value": str(value), "reason": "hub_model_not_allowed"},
        )


def _preflight_problem(pf: PreflightResult) -> ProblemError:
    errs = [
        {"loc": ["body", c.id], "code": c.code, "message": c.message}
        for c in pf.checks
        if c.severity == "error"
    ]
    return ProblemError(
        422,
        ErrorCode.PREFLIGHT_FAILED,
        "; ".join(str(e["message"]) for e in errs),
        errors=errs,
        params={"checks": [c.as_dict() for c in pf.checks]},
    )


# ------------------------------------------------------------------------------------------------
# preflight / create
# ------------------------------------------------------------------------------------------------
@router.post("/runs/preflight", operation_id="preflightRun")
async def preflight_run(
    body: RunCreate, db: DB, principal: CurrentPrincipal, request: Request
) -> dict[str, Any]:
    workspace_role(principal, body.workspace_id, for_list=True)
    require_scope(principal, "runs:write")
    pf = await run_preflight(
        db,
        get_catalog(),
        principal,
        body,
        hf_init_allowlist=_state(request).settings.init_from_hf_allowlist,
        vlm_allowlist=_state(request).settings.vlm_model_allowlist,
    )
    await db.commit()  # persists a queued estimate job (if any)
    return pf.report()


async def _create_run(
    request: Request,
    db: AsyncSession,
    principal: Principal,
    body: RunCreate,
    *,
    parent: Run | None = None,
    base_config: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> Run:
    role = _authorize_create(principal, body)
    if body.priority > 0 and not role_at_least(role, "admin"):
        raise ProblemError(403, ErrorCode.FORBIDDEN, "priority > 0 requires workspace admin")
    run_id = uuid.uuid4()
    cat = get_catalog()
    pf = await run_preflight(
        db,
        cat,
        principal,
        body,
        run_id=str(run_id),
        base_config=base_config,
        hf_init_allowlist=_state(request).settings.init_from_hf_allowlist,
        vlm_allowlist=_state(request).settings.vlm_model_allowlist,
    )
    if pf.config_error is not None:
        raise pf.config_error
    if not pf.ok:
        raise _preflight_problem(pf)
    if pf.resolved is None or pf.dataset is None or pf.dataset_version is None:  # pragma: no cover
        raise ProblemError(500, ErrorCode.INTERNAL_ERROR, "preflight returned no resolution")
    await db.execute(
        text("SELECT pg_advisory_xact_lock(7002, hashtext(:ws))"), {"ws": str(body.workspace_id)}
    )
    number = (
        int(
            (
                await db.scalar(
                    select(func.coalesce(func.max(Run.number), 0)).where(
                        Run.workspace_id == body.workspace_id
                    )
                )
            )
            or 0
        )
        + 1
    )
    cfg = pf.resolved.as_dict()
    export = (body.export or ExportOptions()).model_dump(exclude_none=True)
    cfg["_export"] = export
    if body.init_from is not None and body.init_from.hf_repo_id is not None:
        cfg["_init_from"] = {"hf_repo_id": body.init_from.hf_repo_id}
    init_model = body.init_from.model_id if body.init_from else None
    init_ckpt = body.init_from.checkpoint_id if body.init_from else None
    train = pf.resolved.train
    run = Run(
        id=run_id,
        workspace_id=body.workspace_id,
        number=number,
        name=body.name or f"{pf.dataset.slug}-{body.policy_type}-{number}",
        created_by=principal.user_id,
        dataset_version_id=pf.dataset_version.id,
        policy_type=body.policy_type,
        preset=body.preset if parent is None else parent.preset,
        config=cfg,
        resolved_args=pf.argv,
        parent_run_id=parent.id if parent else None,
        init_from_model_id=init_model,
        init_from_checkpoint_id=init_ckpt,
        heldout_fraction=body.heldout_fraction,
        heldout_episodes=pf.heldout,
        train_episodes=pf.train_eps,
        seed=pf.seed,
        total_steps=int(train["steps"]),
        status=RunStatus.QUEUED,
        priority=body.priority,
        requested_gpu_id=pf.requested_gpu_id,
        required_vram_mb=pf.required_vram_mb,
        mixed_precision_requested=MixedPrecision(str(train.get("mixed_precision", "no"))),
        estimate=pf.estimate,
        idempotency_key=idempotency_key,
    )
    db.add(run)
    await db.flush()
    outbox = Outbox()
    data = {
        "kind": "status",
        "run_id": str(run.id),
        "from": None,
        "to": "queued",
        "reason": "created" if parent is None else "cloned",
        "error_code": None,
        "attempt": 0,
        "gpu_id": None,
        "ts": iso_now(),
    }
    await append_run_event(db, run.id, "status", data, outbox)
    outbox.add(f"hibiscus:ws:{run.workspace_id}", {"event": "run.status", "data": data})
    await _audit(
        db,
        AuditAction.RUN_CREATED,
        principal,
        run,
        policy_type=run.policy_type,
        dataset_version_id=str(run.dataset_version_id),
        parent_run_id=str(parent.id) if parent else None,
    )
    await db.commit()
    await db.refresh(run)
    await _publish(request, outbox, (QUEUE_CHANNEL, str(run.id)))
    return run


@router.post("/runs", operation_id="createRun", status_code=201)
async def create_run(
    body: RunCreate,
    request: Request,
    db: DB,
    principal: CurrentPrincipal,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=64)
    ] = None,
) -> JSONResponse:
    # SEC-auth-05: authorise the *current* request before any replay lookup (a removed member, a PAT
    # bound to another workspace or without runs:write never gets a stored run back).
    _authorize_create(principal, body)
    if idempotency_key is not None:
        replay = await _idempotent_replay(db, principal, body.workspace_id, idempotency_key)
        if replay is not None:
            return replay
    try:
        run = await _create_run(request, db, principal, body, idempotency_key=idempotency_key)
    except IntegrityError as exc:
        # QC-backend-06: a concurrent request with the same key won the unique index; replay it.
        await db.rollback()
        if idempotency_key is None or "uq_runs_idempotency_key" not in str(exc.orig):
            raise
        replay = await _idempotent_replay(db, principal, body.workspace_id, idempotency_key)
        if replay is None:  # pragma: no cover - the winner's row is committed before our insert fails
            raise ProblemError(
                409, ErrorCode.CONFLICT, "a request with this Idempotency-Key is in progress"
            ) from exc
        return replay
    return JSONResponse(
        await _one(db, principal, run), status_code=201, headers={"Location": f"/api/v1/runs/{run.id}"}
    )


def _authorize_create(principal: Principal, body: RunCreate) -> str:
    role = workspace_role(principal, body.workspace_id, for_list=True)
    require_scope(principal, "runs:write")
    if not role_at_least(role, "member"):
        raise ProblemError(403, ErrorCode.FORBIDDEN, "viewers cannot create runs")
    return role


async def _idempotent_replay(
    db: AsyncSession, principal: Principal, workspace_id: uuid.UUID, key: str
) -> JSONResponse | None:
    """The run created by this caller in ``workspace_id`` with ``key`` within 24 h, re-authorised.

    A key older than the replay window is released (cleared on the old run) so it can be reused.
    """
    existing = await db.scalar(
        select(Run).where(
            Run.workspace_id == workspace_id,
            Run.created_by == principal.user_id,
            Run.idempotency_key == key,
        )
    )
    if existing is None:
        return None
    expired = await db.scalar(
        select(Run.id).where(
            Run.id == existing.id, Run.created_at < func.now() - timedelta(seconds=IDEM_TTL_S)
        )
    )
    if expired is not None:
        existing.idempotency_key = None
        await db.flush()
        return None
    run, _ = await load_run(db, principal, existing.id, "runs:read")
    return JSONResponse(
        await _one(db, principal, run), status_code=201, headers={"Location": f"/api/v1/runs/{run.id}"}
    )


# ------------------------------------------------------------------------------------------------
# list / get / update
# ------------------------------------------------------------------------------------------------
@router.get("/runs", operation_id="listRuns")
async def list_runs(
    db: DB,
    principal: CurrentPrincipal,
    workspace_id: uuid.UUID,
    status: str | None = None,
    dataset_id: uuid.UUID | None = None,
    policy_type: str | None = None,
    created_by: Annotated[str | None, Query(max_length=36)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> dict[str, Any]:
    workspace_role(principal, workspace_id, for_list=True)
    require_scope(principal, "runs:read")
    stmt = select(Run).where(Run.workspace_id == workspace_id)
    if status:
        vals = [s for s in status.split(",") if s]
        try:
            stmt = stmt.where(Run.status.in_([RunStatus(v) for v in vals]))
        except ValueError as exc:
            raise ProblemError(
                422,
                ErrorCode.VALIDATION_FAILED,
                "unknown status",
                errors=[{"loc": ["query", "status"], "code": "enum", "message": str(exc)}],
            ) from exc
    if dataset_id:
        stmt = stmt.where(
            Run.dataset_version_id.in_(
                select(DatasetVersion.id).where(DatasetVersion.dataset_id == dataset_id)
            )
        )
    if policy_type:
        stmt = stmt.where(Run.policy_type == policy_type)
    if created_by:
        uid = principal.user_id if created_by == "me" else _uuid(created_by, "created_by")
        stmt = stmt.where(Run.created_by == uid)
    if q:
        stmt = stmt.where(Run.name.ilike("%" + q.replace("%", r"\%").replace("_", r"\_") + "%"))
    if cursor:
        c = decode_cursor(cursor)
        ts = datetime.fromisoformat(c["t"])
        stmt = stmt.where((Run.created_at < ts) | ((Run.created_at == ts) & (Run.id < uuid.UUID(c["i"]))))
    rows = list(
        (await db.execute(stmt.order_by(Run.created_at.desc(), Run.id.desc()).limit(limit + 1))).scalars()
    )
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        nxt = encode_cursor({"t": rows[-1].created_at.isoformat(), "i": str(rows[-1].id)})
    items = await runs_to_dicts(db, rows, principal, principal.workspace_ids_roles)
    return {"items": items, "next_cursor": nxt}


def _uuid(v: str, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(v)
    except ValueError as exc:
        raise ProblemError(
            422,
            ErrorCode.VALIDATION_FAILED,
            f"{name} must be a uuid",
            errors=[{"loc": ["query", name], "code": "format", "message": "uuid"}],
        ) from exc


@router.get("/runs/compare", operation_id="compareRuns")
async def compare_runs(
    db: DB,
    principal: CurrentPrincipal,
    ids: str,
    keys: str = "loss",
    max_points: Annotated[int, Query(ge=50, le=5000)] = 1000,
) -> dict[str, Any]:
    id_list = [_uuid(x, "ids") for x in ids.split(",") if x]
    if not 2 <= len(id_list) <= 8:
        raise ProblemError(
            422,
            ErrorCode.VALIDATION_FAILED,
            "ids must list 2..8 runs",
            errors=[{"loc": ["query", "ids"], "code": "minItems", "message": "2..8"}],
        )
    key_list = [k for k in keys.split(",") if k]
    runs: list[Run] = []
    for rid in id_list:
        run, _ = await load_run(db, principal, rid, "runs:read")
        runs.append(run)
    if len({r.workspace_id for r in runs}) != 1:
        raise ProblemError(
            422,
            ErrorCode.VALIDATION_FAILED,
            "runs must belong to the same workspace",
            errors=[{"loc": ["query", "ids"], "code": "same_workspace", "message": "mixed"}],
        )
    series = []
    for r in runs:
        raw = await load_series(db, r.id, key_list, None, None)
        series.append(
            {"run_id": str(r.id), "series": [downsample_series(k, s, max_points) for k, s in raw.items()]}
        )
    flats = [
        _flatten({"policy": r.config.get("policy", {}), "train": r.config.get("train", {})}) for r in runs
    ]
    paths = sorted({p for f in flats for p in f})
    diff = [
        {"path": p, "values": [f.get(p) for f in flats]}
        for p in paths
        if len({json.dumps(f.get(p), sort_keys=True) for f in flats}) > 1
    ]
    return {
        "runs": await runs_to_dicts(db, runs, principal, principal.workspace_ids_roles),
        "series": series,
        "config_diff": diff,
    }


def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        p = f"{prefix}{k}"
        if isinstance(v, dict) and v:
            out.update(_flatten(v, p + "."))
        else:
            out[p] = v
    return out


@router.get("/runs/{run_id}", operation_id="getRun")
async def get_run(run_id: uuid.UUID, db: DB, principal: CurrentPrincipal) -> dict[str, Any]:
    run, _ = await load_run(db, principal, run_id, "runs:read")
    return await _one(db, principal, run)


@router.patch("/runs/{run_id}", operation_id="updateRun")
async def update_run(
    run_id: uuid.UUID, body: RunUpdate, db: DB, principal: CurrentPrincipal
) -> dict[str, Any]:
    run, role = await load_run_for_update(db, principal, run_id)
    fields = body.model_fields_set
    if ("priority" in fields or "gpu" in fields) and run.status != RunStatus.QUEUED:
        raise invalid_transition(run.status.value, "change priority/GPU of")
    if body.name is not None:
        run.name = body.name
    if "priority" in fields and body.priority is not None:
        if body.priority > 0 and not role_at_least(role, "admin"):
            raise ProblemError(403, ErrorCode.FORBIDDEN, "priority > 0 requires workspace admin")
        run.priority = body.priority
    if "gpu" in fields and body.gpu is not None:
        run.requested_gpu_id = await _resolve_gpu(db, body.gpu, run.policy_type)
    await db.commit()
    await db.refresh(run)
    return await _one(db, principal, run)


async def _resolve_gpu(db: AsyncSession, gpu: str, policy_type: str) -> str | None:
    if gpu == "auto":
        return None
    node = await db.get(GpuNode, gpu)
    if node is None:
        raise ProblemError(422, ErrorCode.GPU_UNKNOWN, f"unknown GPU {gpu}")
    from app.runs.catalog import gpu_support_level

    if gpu_support_level(policy_type, node.total_vram_mb) == "unsupported":
        raise ProblemError(
            422, ErrorCode.GPU_INSUFFICIENT_VRAM, f"{policy_type} is not supported on {node.name}"
        )
    return node.id


# ------------------------------------------------------------------------------------------------
# lifecycle actions
# ------------------------------------------------------------------------------------------------
@router.post("/runs/{run_id}/cancel", operation_id="cancelRun", status_code=202)
async def cancel_run(
    run_id: uuid.UUID, request: Request, db: DB, principal: CurrentPrincipal
) -> dict[str, Any]:
    run, _ = await load_run_for_update(db, principal, run_id)
    outbox = Outbox()
    st = run.status
    extra_pub: list[tuple[str, str]] = []
    if st in (RunStatus.CANCELLING, RunStatus.CANCELLED):
        pass
    elif st in (RunStatus.QUEUED, RunStatus.PAUSED):
        await transition(
            db,
            run,
            from_statuses=[st],
            to=RunStatus.CANCELLED,
            outbox=outbox,
            reason="user_cancel",
            extra={"desired_state": "cancel"},
        )
    elif st in (RunStatus.PREPARING, RunStatus.RUNNING, RunStatus.PAUSING, RunStatus.EXPORTING):
        await transition(
            db,
            run,
            from_statuses=[st],
            to=RunStatus.CANCELLING,
            outbox=outbox,
            reason="user_cancel",
            extra={"desired_state": "cancel"},
        )
        if run.gpu_node_id:
            extra_pub.append(
                (
                    control_channel(run.gpu_node_id),
                    json.dumps({"run_id": str(run.id), "desired_state": "cancel"}),
                )
            )
    else:
        raise invalid_transition(st.value, "cancel")
    if st not in (RunStatus.CANCELLING, RunStatus.CANCELLED):
        await _audit(db, AuditAction.RUN_CANCELLED, principal, run, from_status=st.value)
    await db.commit()
    await _publish(request, outbox, *extra_pub)
    await db.refresh(run)
    return await _one(db, principal, run)


@router.post("/runs/{run_id}/pause", operation_id="pauseRun", status_code=202)
async def pause_run(
    run_id: uuid.UUID,
    request: Request,
    db: DB,
    principal: CurrentPrincipal,
    body: Annotated[RunPauseRequest | None, Body()] = None,
) -> dict[str, Any]:
    mode = (body or RunPauseRequest()).mode
    desired = "pause_now" if mode == "now" else "pause"
    run, _ = await load_run_for_update(db, principal, run_id)
    outbox = Outbox()
    st = run.status
    if st in (RunStatus.PREPARING, RunStatus.RUNNING):
        await transition(
            db,
            run,
            from_statuses=[st],
            to=RunStatus.PAUSING,
            outbox=outbox,
            reason="user_pause",
            extra={"desired_state": desired},
        )
    elif st == RunStatus.PAUSING:
        if desired == "pause_now" and run.desired_state != "pause_now":
            run.desired_state = "pause_now"
    else:
        raise invalid_transition(st.value, "pause")
    await _audit(db, AuditAction.RUN_PAUSED, principal, run, mode=mode)
    await db.commit()
    pubs = []
    if run.gpu_node_id:
        pubs.append(
            (control_channel(run.gpu_node_id), json.dumps({"run_id": str(run.id), "desired_state": desired}))
        )
    await _publish(request, outbox, *pubs)
    await db.refresh(run)
    return await _one(db, principal, run)


@router.post("/runs/{run_id}/resume", operation_id="resumeRun", status_code=202)
async def resume_run(
    run_id: uuid.UUID,
    request: Request,
    db: DB,
    principal: CurrentPrincipal,
    body: Annotated[RunResumeRequest | None, Body()] = None,
) -> dict[str, Any]:
    req = body or RunResumeRequest()
    run, _ = await load_run_for_update(db, principal, run_id)
    st = run.status
    last = await db.scalar(
        select(Checkpoint.step).where(Checkpoint.run_id == run.id, Checkpoint.is_last.is_(True))
    )
    if st == RunStatus.FAILED and last is None:
        raise ProblemError(409, ErrorCode.RUN_NOT_RESUMABLE, "no checkpoint to resume from")
    if st not in (RunStatus.PAUSED, RunStatus.FAILED):
        raise invalid_transition(st.value, "resume")
    _require_allowed_hf_init(request, run)
    q = await effective_quota(db, run.workspace_id, run.created_by)
    if await gpu_hours_this_month(db, run.workspace_id, run.created_by) >= float(q["gpu_hours_per_month"]):
        raise ProblemError(403, ErrorCode.QUOTA_EXCEEDED, "monthly GPU hours exhausted")
    extra: dict[str, Any] = {"desired_state": "run", "queued_at": func.now(), "gpu_node_id": None}
    if st == RunStatus.FAILED:
        extra.update(
            infra_retries_used=0,
            resume_checkpoint_step=last,
            error_code=None,
            error_message=None,
            finished_at=None,
        )
    elif run.error_code is not None:  # paused by the worker for quota_exceeded (run-lifecycle §6)
        extra["error_code"] = None
    if req.total_steps is not None:
        if req.total_steps <= run.current_step:
            raise ProblemError(
                422,
                ErrorCode.VALIDATION_FAILED,
                "total_steps must be > current_step",
                errors=[{"loc": ["body", "total_steps"], "code": "minimum", "message": "> current_step"}],
            )
        cfg = dict(run.config)
        cfg["train"] = {**cfg.get("train", {}), "steps": req.total_steps}
        extra.update(total_steps=req.total_steps, config=cfg)
    if req.gpu is not None:
        extra["requested_gpu_id"] = await _resolve_gpu(db, req.gpu, run.policy_type)
    outbox = Outbox()
    await transition(
        db, run, from_statuses=[st], to=RunStatus.QUEUED, outbox=outbox, reason="user_resume", extra=extra
    )
    await _audit(db, AuditAction.RUN_RESUMED, principal, run, from_status=st.value)
    await db.commit()
    await _publish(request, outbox, (QUEUE_CHANNEL, str(run.id)))
    await db.refresh(run)
    return await _one(db, principal, run)


@router.post("/runs/{run_id}/clone", operation_id="cloneRun", status_code=201)
async def clone_run(
    run_id: uuid.UUID,
    request: Request,
    db: DB,
    principal: CurrentPrincipal,
    body: Annotated[RunCloneRequest | None, Body()] = None,
) -> JSONResponse:
    req = body or RunCloneRequest()
    src, _ = await load_run(db, principal, run_id, "runs:write")
    from app.runs.schemas import InitFrom, RunConfig

    init_from: InitFrom | None
    if "init_from" in req.model_fields_set:
        init_from = req.init_from
    elif src.init_from_model_id:
        init_from = InitFrom(model_id=src.init_from_model_id)
    elif src.init_from_checkpoint_id:
        init_from = InitFrom(checkpoint_id=src.init_from_checkpoint_id)
    elif isinstance(src.config.get("_init_from"), dict):
        init_from = InitFrom(**src.config["_init_from"])
    else:
        init_from = None
    overrides = req.config or {}
    base = {"policy": src.config.get("policy", {}), "train": src.config.get("train", {})}
    export = req.export or ExportOptions(**(src.config.get("_export") or {}))
    create = RunCreate(
        workspace_id=src.workspace_id,
        name=req.name or f"{src.name} (clone)"[:100],
        dataset_version_id=req.dataset_version_id or src.dataset_version_id,
        policy_type=src.policy_type,  # type: ignore[arg-type]  # stored value is a valid PolicyType
        preset=None,
        config=RunConfig(policy=overrides.get("policy", {}), train=overrides.get("train", {})),
        heldout_fraction=req.heldout_fraction if req.heldout_fraction is not None else src.heldout_fraction,
        gpu=req.gpu or (src.requested_gpu_id or "auto"),
        priority=req.priority if req.priority is not None else min(src.priority, 0),
        init_from=init_from,
        export=export,
    )
    run = await _create_run(request, db, principal, create, parent=src, base_config=deep_merge(base, {}))
    return JSONResponse(
        await _one(db, principal, run), status_code=201, headers={"Location": f"/api/v1/runs/{run.id}"}
    )


# ------------------------------------------------------------------------------------------------
# manifest / checkpoints
# ------------------------------------------------------------------------------------------------
@router.get("/runs/{run_id}/manifest", operation_id="getRunManifest")
async def get_manifest(run_id: uuid.UUID, db: DB, principal: CurrentPrincipal) -> Any:
    run, _ = await load_run(db, principal, run_id, "runs:read")
    if not run.manifest:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "manifest not written yet")
    return {k: v for k, v in run.manifest.items() if not k.startswith("_")}


@router.get("/runs/{run_id}/checkpoints", operation_id="listCheckpoints")
async def list_checkpoints(run_id: uuid.UUID, db: DB, principal: CurrentPrincipal) -> dict[str, Any]:
    run, _ = await load_run(db, principal, run_id, "runs:read")
    ckpts = list(
        (
            await db.execute(select(Checkpoint).where(Checkpoint.run_id == run.id).order_by(Checkpoint.step))
        ).scalars()
    )
    model_rows = await db.execute(
        select(Model.checkpoint_id, Model.id).where(Model.run_id == run.id, Model.deleted_at.is_(None))
    )
    models: dict[uuid.UUID, uuid.UUID] = {row[0]: row[1] for row in model_rows.all()}
    return {"items": [checkpoint_to_dict(c, models.get(c.id)) for c in ckpts]}


async def _checkpoint(db: AsyncSession, run: Run, step: int) -> Checkpoint:
    c = await db.scalar(select(Checkpoint).where(Checkpoint.run_id == run.id, Checkpoint.step == step))
    if c is None:
        raise ProblemError(404, ErrorCode.CHECKPOINT_NOT_FOUND, f"no checkpoint at step {step}")
    return c


async def _check_gpu_job_quota(db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """N6: user-requested GPU jobs (export / eval) obey the requester's GPU-hour quota, and at most
    ``max_concurrent_runs`` of them may be queued or running per user and workspace."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(7003, hashtext(:k))"), {"k": f"{workspace_id}:{user_id}"}
    )
    q = await effective_quota(db, workspace_id, user_id)
    if await gpu_hours_this_month(db, workspace_id, user_id) >= float(q["gpu_hours_per_month"]):
        raise ProblemError(
            403, ErrorCode.QUOTA_EXCEEDED, "monthly GPU hours exhausted", params={"reason": "gpu_hours"}
        )
    outstanding = await db.scalar(
        select(func.count(Job.id)).where(
            Job.workspace_id == workspace_id,
            Job.created_by == user_id,
            Job.resource == JobResource.GPU,
            Job.kind.in_([JobKind.EXPORT_MODEL, JobKind.EVAL_CHECKPOINT]),
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            Job.payload["user_requested"].as_boolean().is_(True),
        )
    )
    limit = int(q["max_concurrent_runs"])
    if int(outstanding or 0) >= limit:
        raise ProblemError(
            403,
            ErrorCode.QUOTA_EXCEEDED,
            f"at most {limit} export/eval job(s) may be queued or running at a time",
            params={"reason": "concurrent_jobs", "limit": limit},
        )


@router.post("/runs/{run_id}/checkpoints/{step}/export", operation_id="exportCheckpoint", status_code=202)
async def export_checkpoint(
    run_id: uuid.UUID,
    step: Annotated[int, Path(ge=1)],
    request: Request,
    db: DB,
    principal: CurrentPrincipal,
    body: Annotated[ExportOptions | None, Body()] = None,
) -> Response:
    run, role = await load_run(db, principal, run_id, "runs:write")
    require_can_mutate(run, principal, role)
    ckpt = await _checkpoint(db, run, step)
    # QC-backend-07: serialise concurrent exports of one checkpoint on its row, so the existence
    # check below sees a model committed by a racing request (instead of both inserting).
    await db.execute(select(Checkpoint.id).where(Checkpoint.id == ckpt.id).with_for_update())
    existing = await db.scalar(
        select(Model).where(Model.checkpoint_id == ckpt.id, Model.deleted_at.is_(None))
    )
    from app.db.models import Dataset

    dv = await db.get(DatasetVersion, run.dataset_version_id)
    ds = await db.get(Dataset, dv.dataset_id) if dv else None
    if existing is not None and existing.status != ModelStatus.FAILED:
        return JSONResponse(
            model_to_dict(existing, run=run, dataset=ds, version=dv, creator=None), status_code=200
        )
    await _check_gpu_job_quota(db, run.workspace_id, principal.user_id)
    if existing is not None:
        # QC-backend-02: a failed export can be retried; the failed model row is retired.
        existing.deleted_at = func.now()
        await db.flush()
    opts = (body or ExportOptions(**(run.config.get("_export") or {}))).model_dump(exclude_none=True)
    model_name = opts.get("model_name") or f"{ds.slug if ds else 'model'}_{run.policy_type}"
    onnx = (
        OnnxStatus.NOT_SUPPORTED
        if POLICY_META[run.policy_type].onnx == "none" or not opts.get("onnx", True)
        else OnnxStatus.PENDING
    )
    model = Model(
        workspace_id=run.workspace_id,
        run_id=run.id,
        checkpoint_id=ckpt.id,
        name=f"{model_name}-r{run.number}-step{ckpt.step}",
        policy_type=run.policy_type,
        step=ckpt.step,
        status=ModelStatus.PENDING,
        onnx_status=onnx,
        created_by=principal.user_id,
    )
    db.add(model)
    try:
        await db.flush()
    except IntegrityError as exc:  # defence in depth: never a 500 for a lost race
        await db.rollback()
        if "uq_models_checkpoint_live" not in str(exc.orig):
            raise
        raise ProblemError(
            409, ErrorCode.CONFLICT, "an export of this checkpoint is already in progress"
        ) from exc
    db.add(
        Job(
            workspace_id=run.workspace_id,
            kind=JobKind.EXPORT_MODEL,
            resource=JobResource.GPU,
            payload={
                "checkpoint_id": str(ckpt.id),
                "step": ckpt.step,
                "options": opts,
                "user_requested": True,
            },
            run_id=run.id,
            model_id=model.id,
            created_by=principal.user_id,
        )
    )
    await db.commit()
    await db.refresh(model)
    await _publish(request, Outbox(), (QUEUE_CHANNEL, f"job:{model.id}"))
    return JSONResponse(model_to_dict(model, run=run, dataset=ds, version=dv, creator=None), status_code=202)


@router.post("/runs/{run_id}/checkpoints/{step}/eval", operation_id="evalCheckpoint", status_code=202)
async def eval_checkpoint(
    run_id: uuid.UUID, step: Annotated[int, Path(ge=1)], request: Request, db: DB, principal: CurrentPrincipal
) -> dict[str, Any]:
    run, role = await load_run(db, principal, run_id, "runs:write")
    require_can_mutate(run, principal, role)
    ckpt = await _checkpoint(db, run, step)
    busy = await db.scalar(
        select(Job.id).where(
            Job.kind == JobKind.EVAL_CHECKPOINT,
            Job.run_id == run.id,
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            Job.payload["checkpoint_id"].astext == str(ckpt.id),
        )
    )
    if busy is not None:
        raise ProblemError(409, ErrorCode.CONFLICT, "an eval of this checkpoint is already queued")
    await _check_gpu_job_quota(db, run.workspace_id, principal.user_id)
    job = Job(
        workspace_id=run.workspace_id,
        kind=JobKind.EVAL_CHECKPOINT,
        resource=JobResource.GPU,
        payload={"checkpoint_id": str(ckpt.id), "step": ckpt.step, "user_requested": True},
        run_id=run.id,
        created_by=principal.user_id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await _publish(request, Outbox(), (QUEUE_CHANNEL, f"job:{job.id}"))
    return job_to_dict(job)


@router.get("/runs/{run_id}/checkpoints/{step}/eval-result", operation_id="getCheckpointEval")
async def get_checkpoint_eval(
    run_id: uuid.UUID, step: Annotated[int, Path(ge=1)], db: DB, principal: CurrentPrincipal
) -> Any:
    run, _ = await load_run(db, principal, run_id, "runs:read")
    ckpt = await _checkpoint(db, run, step)
    if not ckpt.eval_metrics:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "no eval result for this checkpoint")
    return ckpt.eval_metrics
