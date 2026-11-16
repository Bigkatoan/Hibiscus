from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.mixed_precision import MixedPrecision
from ..models.policy_type import PolicyType
from ..models.run_allowed_actions_item import RunAllowedActionsItem
from ..models.run_desired_state import RunDesiredState
from ..models.run_error_code import RunErrorCode
from ..models.run_status import RunStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.export_options import ExportOptions
    from ..models.resource_estimate import ResourceEstimate
    from ..models.run_config import RunConfig
    from ..models.run_dataset import RunDataset
    from ..models.run_latest_metrics import RunLatestMetrics
    from ..models.run_progress import RunProgress
    from ..models.user_ref import UserRef


T = TypeVar("T", bound="Run")


@_attrs_define
class Run:
    """
    Attributes:
        id (UUID):
        workspace_id (UUID):
        number (int): Per-workspace sequence, shown as #42
        name (str):
        status (RunStatus): State machine in docs/spec/run-lifecycle.md
        policy_type (PolicyType):
        dataset_version_id (UUID):
        dataset (RunDataset):
        config (RunConfig):
        progress (RunProgress):
        priority (int):
        attempt (int): Number of worker attempts so far (0 while first queued)
        created_by (UserRef):
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        status_changed_at (datetime.datetime | Unset):
        desired_state (RunDesiredState | Unset):
        error_code (None | RunErrorCode | Unset):
        error_message (None | str | Unset):
        preset (None | str | Unset):
        heldout_episodes (list[int] | Unset):
        seed (int | Unset):
        latest_metrics (RunLatestMetrics | Unset): key -> last value
        gpu_id (None | str | Unset):
        requested_gpu (str | Unset):
        mixed_precision_requested (MixedPrecision | Unset):
        mixed_precision_effective (MixedPrecision | None | Unset):
        queue_position (int | None | Unset):
        infra_retries_used (int | Unset):
        estimate (None | ResourceEstimate | Unset):
        parent_run_id (None | Unset | UUID):
        init_from (Any | None | Unset):
        export (ExportOptions | Unset):
        model_id (None | Unset | UUID): Model built from the final checkpoint
        gpu_seconds (float | Unset):
        queued_at (datetime.datetime | Unset):
        started_at (datetime.datetime | None | Unset):
        finished_at (datetime.datetime | None | Unset):
        allowed_actions (list[RunAllowedActionsItem] | Unset): Actions valid for the caller now (UI enables buttons from
            this)
    """

    id: UUID
    workspace_id: UUID
    number: int
    name: str
    status: RunStatus
    policy_type: PolicyType
    dataset_version_id: UUID
    dataset: RunDataset
    config: RunConfig
    progress: RunProgress
    priority: int
    attempt: int
    created_by: UserRef
    created_at: datetime.datetime
    updated_at: datetime.datetime
    status_changed_at: datetime.datetime | Unset = UNSET
    desired_state: RunDesiredState | Unset = UNSET
    error_code: None | RunErrorCode | Unset = UNSET
    error_message: None | str | Unset = UNSET
    preset: None | str | Unset = UNSET
    heldout_episodes: list[int] | Unset = UNSET
    seed: int | Unset = UNSET
    latest_metrics: RunLatestMetrics | Unset = UNSET
    gpu_id: None | str | Unset = UNSET
    requested_gpu: str | Unset = UNSET
    mixed_precision_requested: MixedPrecision | Unset = UNSET
    mixed_precision_effective: MixedPrecision | None | Unset = UNSET
    queue_position: int | None | Unset = UNSET
    infra_retries_used: int | Unset = UNSET
    estimate: None | ResourceEstimate | Unset = UNSET
    parent_run_id: None | Unset | UUID = UNSET
    init_from: Any | None | Unset = UNSET
    export: ExportOptions | Unset = UNSET
    model_id: None | Unset | UUID = UNSET
    gpu_seconds: float | Unset = UNSET
    queued_at: datetime.datetime | Unset = UNSET
    started_at: datetime.datetime | None | Unset = UNSET
    finished_at: datetime.datetime | None | Unset = UNSET
    allowed_actions: list[RunAllowedActionsItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.resource_estimate import ResourceEstimate

        id = str(self.id)

        workspace_id = str(self.workspace_id)

        number = self.number

        name = self.name

        status = self.status.value

        policy_type = self.policy_type.value

        dataset_version_id = str(self.dataset_version_id)

        dataset = self.dataset.to_dict()

        config = self.config.to_dict()

        progress = self.progress.to_dict()

        priority = self.priority

        attempt = self.attempt

        created_by = self.created_by.to_dict()

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        status_changed_at: str | Unset = UNSET
        if not isinstance(self.status_changed_at, Unset):
            status_changed_at = self.status_changed_at.isoformat()

        desired_state: str | Unset = UNSET
        if not isinstance(self.desired_state, Unset):
            desired_state = self.desired_state.value

        error_code: None | str | Unset
        if isinstance(self.error_code, Unset):
            error_code = UNSET
        elif isinstance(self.error_code, RunErrorCode):
            error_code = self.error_code.value
        else:
            error_code = self.error_code

        error_message: None | str | Unset
        if isinstance(self.error_message, Unset):
            error_message = UNSET
        else:
            error_message = self.error_message

        preset: None | str | Unset
        if isinstance(self.preset, Unset):
            preset = UNSET
        else:
            preset = self.preset

        heldout_episodes: list[int] | Unset = UNSET
        if not isinstance(self.heldout_episodes, Unset):
            heldout_episodes = self.heldout_episodes

        seed = self.seed

        latest_metrics: dict[str, Any] | Unset = UNSET
        if not isinstance(self.latest_metrics, Unset):
            latest_metrics = self.latest_metrics.to_dict()

        gpu_id: None | str | Unset
        if isinstance(self.gpu_id, Unset):
            gpu_id = UNSET
        else:
            gpu_id = self.gpu_id

        requested_gpu = self.requested_gpu

        mixed_precision_requested: str | Unset = UNSET
        if not isinstance(self.mixed_precision_requested, Unset):
            mixed_precision_requested = self.mixed_precision_requested.value

        mixed_precision_effective: None | str | Unset
        if isinstance(self.mixed_precision_effective, Unset):
            mixed_precision_effective = UNSET
        elif isinstance(self.mixed_precision_effective, MixedPrecision):
            mixed_precision_effective = self.mixed_precision_effective.value
        else:
            mixed_precision_effective = self.mixed_precision_effective

        queue_position: int | None | Unset
        if isinstance(self.queue_position, Unset):
            queue_position = UNSET
        else:
            queue_position = self.queue_position

        infra_retries_used = self.infra_retries_used

        estimate: dict[str, Any] | None | Unset
        if isinstance(self.estimate, Unset):
            estimate = UNSET
        elif isinstance(self.estimate, ResourceEstimate):
            estimate = self.estimate.to_dict()
        else:
            estimate = self.estimate

        parent_run_id: None | str | Unset
        if isinstance(self.parent_run_id, Unset):
            parent_run_id = UNSET
        elif isinstance(self.parent_run_id, UUID):
            parent_run_id = str(self.parent_run_id)
        else:
            parent_run_id = self.parent_run_id

        init_from: Any | None | Unset
        if isinstance(self.init_from, Unset):
            init_from = UNSET
        else:
            init_from = self.init_from

        export: dict[str, Any] | Unset = UNSET
        if not isinstance(self.export, Unset):
            export = self.export.to_dict()

        model_id: None | str | Unset
        if isinstance(self.model_id, Unset):
            model_id = UNSET
        elif isinstance(self.model_id, UUID):
            model_id = str(self.model_id)
        else:
            model_id = self.model_id

        gpu_seconds = self.gpu_seconds

        queued_at: str | Unset = UNSET
        if not isinstance(self.queued_at, Unset):
            queued_at = self.queued_at.isoformat()

        started_at: None | str | Unset
        if isinstance(self.started_at, Unset):
            started_at = UNSET
        elif isinstance(self.started_at, datetime.datetime):
            started_at = self.started_at.isoformat()
        else:
            started_at = self.started_at

        finished_at: None | str | Unset
        if isinstance(self.finished_at, Unset):
            finished_at = UNSET
        elif isinstance(self.finished_at, datetime.datetime):
            finished_at = self.finished_at.isoformat()
        else:
            finished_at = self.finished_at

        allowed_actions: list[str] | Unset = UNSET
        if not isinstance(self.allowed_actions, Unset):
            allowed_actions = []
            for allowed_actions_item_data in self.allowed_actions:
                allowed_actions_item = allowed_actions_item_data.value
                allowed_actions.append(allowed_actions_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "workspace_id": workspace_id,
                "number": number,
                "name": name,
                "status": status,
                "policy_type": policy_type,
                "dataset_version_id": dataset_version_id,
                "dataset": dataset,
                "config": config,
                "progress": progress,
                "priority": priority,
                "attempt": attempt,
                "created_by": created_by,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
        if status_changed_at is not UNSET:
            field_dict["status_changed_at"] = status_changed_at
        if desired_state is not UNSET:
            field_dict["desired_state"] = desired_state
        if error_code is not UNSET:
            field_dict["error_code"] = error_code
        if error_message is not UNSET:
            field_dict["error_message"] = error_message
        if preset is not UNSET:
            field_dict["preset"] = preset
        if heldout_episodes is not UNSET:
            field_dict["heldout_episodes"] = heldout_episodes
        if seed is not UNSET:
            field_dict["seed"] = seed
        if latest_metrics is not UNSET:
            field_dict["latest_metrics"] = latest_metrics
        if gpu_id is not UNSET:
            field_dict["gpu_id"] = gpu_id
        if requested_gpu is not UNSET:
            field_dict["requested_gpu"] = requested_gpu
        if mixed_precision_requested is not UNSET:
            field_dict["mixed_precision_requested"] = mixed_precision_requested
        if mixed_precision_effective is not UNSET:
            field_dict["mixed_precision_effective"] = mixed_precision_effective
        if queue_position is not UNSET:
            field_dict["queue_position"] = queue_position
        if infra_retries_used is not UNSET:
            field_dict["infra_retries_used"] = infra_retries_used
        if estimate is not UNSET:
            field_dict["estimate"] = estimate
        if parent_run_id is not UNSET:
            field_dict["parent_run_id"] = parent_run_id
        if init_from is not UNSET:
            field_dict["init_from"] = init_from
        if export is not UNSET:
            field_dict["export"] = export
        if model_id is not UNSET:
            field_dict["model_id"] = model_id
        if gpu_seconds is not UNSET:
            field_dict["gpu_seconds"] = gpu_seconds
        if queued_at is not UNSET:
            field_dict["queued_at"] = queued_at
        if started_at is not UNSET:
            field_dict["started_at"] = started_at
        if finished_at is not UNSET:
            field_dict["finished_at"] = finished_at
        if allowed_actions is not UNSET:
            field_dict["allowed_actions"] = allowed_actions

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.export_options import ExportOptions
        from ..models.resource_estimate import ResourceEstimate
        from ..models.run_config import RunConfig
        from ..models.run_dataset import RunDataset
        from ..models.run_latest_metrics import RunLatestMetrics
        from ..models.run_progress import RunProgress
        from ..models.user_ref import UserRef

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        workspace_id = UUID(d.pop("workspace_id"))

        number = d.pop("number")

        name = d.pop("name")

        status = RunStatus(d.pop("status"))

        policy_type = PolicyType(d.pop("policy_type"))

        dataset_version_id = UUID(d.pop("dataset_version_id"))

        dataset = RunDataset.from_dict(d.pop("dataset"))

        config = RunConfig.from_dict(d.pop("config"))

        progress = RunProgress.from_dict(d.pop("progress"))

        priority = d.pop("priority")

        attempt = d.pop("attempt")

        created_by = UserRef.from_dict(d.pop("created_by"))

        created_at = isoparse(d.pop("created_at"))

        updated_at = isoparse(d.pop("updated_at"))

        _status_changed_at = d.pop("status_changed_at", UNSET)
        status_changed_at: datetime.datetime | Unset
        if isinstance(_status_changed_at, Unset):
            status_changed_at = UNSET
        else:
            status_changed_at = isoparse(_status_changed_at)

        _desired_state = d.pop("desired_state", UNSET)
        desired_state: RunDesiredState | Unset
        if isinstance(_desired_state, Unset):
            desired_state = UNSET
        else:
            desired_state = RunDesiredState(_desired_state)

        def _parse_error_code(data: object) -> None | RunErrorCode | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                error_code_type_0 = RunErrorCode(data)

                return error_code_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RunErrorCode | Unset, data)

        error_code = _parse_error_code(d.pop("error_code", UNSET))

        def _parse_error_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_message = _parse_error_message(d.pop("error_message", UNSET))

        def _parse_preset(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        preset = _parse_preset(d.pop("preset", UNSET))

        heldout_episodes = cast(list[int], d.pop("heldout_episodes", UNSET))

        seed = d.pop("seed", UNSET)

        _latest_metrics = d.pop("latest_metrics", UNSET)
        latest_metrics: RunLatestMetrics | Unset
        if isinstance(_latest_metrics, Unset):
            latest_metrics = UNSET
        else:
            latest_metrics = RunLatestMetrics.from_dict(_latest_metrics)

        def _parse_gpu_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        gpu_id = _parse_gpu_id(d.pop("gpu_id", UNSET))

        requested_gpu = d.pop("requested_gpu", UNSET)

        _mixed_precision_requested = d.pop("mixed_precision_requested", UNSET)
        mixed_precision_requested: MixedPrecision | Unset
        if isinstance(_mixed_precision_requested, Unset):
            mixed_precision_requested = UNSET
        else:
            mixed_precision_requested = MixedPrecision(_mixed_precision_requested)

        def _parse_mixed_precision_effective(
            data: object,
        ) -> MixedPrecision | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                mixed_precision_effective_type_0 = MixedPrecision(data)

                return mixed_precision_effective_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MixedPrecision | None | Unset, data)

        mixed_precision_effective = _parse_mixed_precision_effective(
            d.pop("mixed_precision_effective", UNSET)
        )

        def _parse_queue_position(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        queue_position = _parse_queue_position(d.pop("queue_position", UNSET))

        infra_retries_used = d.pop("infra_retries_used", UNSET)

        def _parse_estimate(data: object) -> None | ResourceEstimate | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                estimate_type_0 = ResourceEstimate.from_dict(data)

                return estimate_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ResourceEstimate | Unset, data)

        estimate = _parse_estimate(d.pop("estimate", UNSET))

        def _parse_parent_run_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                parent_run_id_type_0 = UUID(data)

                return parent_run_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        parent_run_id = _parse_parent_run_id(d.pop("parent_run_id", UNSET))

        def _parse_init_from(data: object) -> Any | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Any | None | Unset, data)

        init_from = _parse_init_from(d.pop("init_from", UNSET))

        _export = d.pop("export", UNSET)
        export: ExportOptions | Unset
        if isinstance(_export, Unset):
            export = UNSET
        else:
            export = ExportOptions.from_dict(_export)

        def _parse_model_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                model_id_type_0 = UUID(data)

                return model_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        model_id = _parse_model_id(d.pop("model_id", UNSET))

        gpu_seconds = d.pop("gpu_seconds", UNSET)

        _queued_at = d.pop("queued_at", UNSET)
        queued_at: datetime.datetime | Unset
        if isinstance(_queued_at, Unset):
            queued_at = UNSET
        else:
            queued_at = isoparse(_queued_at)

        def _parse_started_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                started_at_type_0 = isoparse(data)

                return started_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        started_at = _parse_started_at(d.pop("started_at", UNSET))

        def _parse_finished_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                finished_at_type_0 = isoparse(data)

                return finished_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        finished_at = _parse_finished_at(d.pop("finished_at", UNSET))

        _allowed_actions = d.pop("allowed_actions", UNSET)
        allowed_actions: list[RunAllowedActionsItem] | Unset = UNSET
        if _allowed_actions is not UNSET:
            allowed_actions = []
            for allowed_actions_item_data in _allowed_actions:
                allowed_actions_item = RunAllowedActionsItem(allowed_actions_item_data)

                allowed_actions.append(allowed_actions_item)

        run = cls(
            id=id,
            workspace_id=workspace_id,
            number=number,
            name=name,
            status=status,
            policy_type=policy_type,
            dataset_version_id=dataset_version_id,
            dataset=dataset,
            config=config,
            progress=progress,
            priority=priority,
            attempt=attempt,
            created_by=created_by,
            created_at=created_at,
            updated_at=updated_at,
            status_changed_at=status_changed_at,
            desired_state=desired_state,
            error_code=error_code,
            error_message=error_message,
            preset=preset,
            heldout_episodes=heldout_episodes,
            seed=seed,
            latest_metrics=latest_metrics,
            gpu_id=gpu_id,
            requested_gpu=requested_gpu,
            mixed_precision_requested=mixed_precision_requested,
            mixed_precision_effective=mixed_precision_effective,
            queue_position=queue_position,
            infra_retries_used=infra_retries_used,
            estimate=estimate,
            parent_run_id=parent_run_id,
            init_from=init_from,
            export=export,
            model_id=model_id,
            gpu_seconds=gpu_seconds,
            queued_at=queued_at,
            started_at=started_at,
            finished_at=finished_at,
            allowed_actions=allowed_actions,
        )

        run.additional_properties = d
        return run

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
