from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.job_kind import JobKind
from ..models.job_status import JobStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.job_result_type_0 import JobResultType0


T = TypeVar("T", bound="Job")


@_attrs_define
class Job:
    """
    Attributes:
        id (UUID):
        workspace_id (UUID):
        kind (JobKind):
        status (JobStatus):
        progress (float):
        created_at (datetime.datetime):
        stage (None | str | Unset): Human stage label key, e.g. `validate.decode`
        error_code (None | str | Unset):
        error_message (None | str | Unset):
        result (JobResultType0 | None | Unset):
        run_id (None | Unset | UUID):
        dataset_version_id (None | Unset | UUID):
        model_id (None | Unset | UUID):
        started_at (datetime.datetime | None | Unset):
        finished_at (datetime.datetime | None | Unset):
    """

    id: UUID
    workspace_id: UUID
    kind: JobKind
    status: JobStatus
    progress: float
    created_at: datetime.datetime
    stage: None | str | Unset = UNSET
    error_code: None | str | Unset = UNSET
    error_message: None | str | Unset = UNSET
    result: JobResultType0 | None | Unset = UNSET
    run_id: None | Unset | UUID = UNSET
    dataset_version_id: None | Unset | UUID = UNSET
    model_id: None | Unset | UUID = UNSET
    started_at: datetime.datetime | None | Unset = UNSET
    finished_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.job_result_type_0 import JobResultType0

        id = str(self.id)

        workspace_id = str(self.workspace_id)

        kind = self.kind.value

        status = self.status.value

        progress = self.progress

        created_at = self.created_at.isoformat()

        stage: None | str | Unset
        if isinstance(self.stage, Unset):
            stage = UNSET
        else:
            stage = self.stage

        error_code: None | str | Unset
        if isinstance(self.error_code, Unset):
            error_code = UNSET
        else:
            error_code = self.error_code

        error_message: None | str | Unset
        if isinstance(self.error_message, Unset):
            error_message = UNSET
        else:
            error_message = self.error_message

        result: dict[str, Any] | None | Unset
        if isinstance(self.result, Unset):
            result = UNSET
        elif isinstance(self.result, JobResultType0):
            result = self.result.to_dict()
        else:
            result = self.result

        run_id: None | str | Unset
        if isinstance(self.run_id, Unset):
            run_id = UNSET
        elif isinstance(self.run_id, UUID):
            run_id = str(self.run_id)
        else:
            run_id = self.run_id

        dataset_version_id: None | str | Unset
        if isinstance(self.dataset_version_id, Unset):
            dataset_version_id = UNSET
        elif isinstance(self.dataset_version_id, UUID):
            dataset_version_id = str(self.dataset_version_id)
        else:
            dataset_version_id = self.dataset_version_id

        model_id: None | str | Unset
        if isinstance(self.model_id, Unset):
            model_id = UNSET
        elif isinstance(self.model_id, UUID):
            model_id = str(self.model_id)
        else:
            model_id = self.model_id

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

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "workspace_id": workspace_id,
                "kind": kind,
                "status": status,
                "progress": progress,
                "created_at": created_at,
            }
        )
        if stage is not UNSET:
            field_dict["stage"] = stage
        if error_code is not UNSET:
            field_dict["error_code"] = error_code
        if error_message is not UNSET:
            field_dict["error_message"] = error_message
        if result is not UNSET:
            field_dict["result"] = result
        if run_id is not UNSET:
            field_dict["run_id"] = run_id
        if dataset_version_id is not UNSET:
            field_dict["dataset_version_id"] = dataset_version_id
        if model_id is not UNSET:
            field_dict["model_id"] = model_id
        if started_at is not UNSET:
            field_dict["started_at"] = started_at
        if finished_at is not UNSET:
            field_dict["finished_at"] = finished_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.job_result_type_0 import JobResultType0

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        workspace_id = UUID(d.pop("workspace_id"))

        kind = JobKind(d.pop("kind"))

        status = JobStatus(d.pop("status"))

        progress = d.pop("progress")

        created_at = isoparse(d.pop("created_at"))

        def _parse_stage(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        stage = _parse_stage(d.pop("stage", UNSET))

        def _parse_error_code(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_code = _parse_error_code(d.pop("error_code", UNSET))

        def _parse_error_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_message = _parse_error_message(d.pop("error_message", UNSET))

        def _parse_result(data: object) -> JobResultType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                result_type_0 = JobResultType0.from_dict(data)

                return result_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(JobResultType0 | None | Unset, data)

        result = _parse_result(d.pop("result", UNSET))

        def _parse_run_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                run_id_type_0 = UUID(data)

                return run_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        run_id = _parse_run_id(d.pop("run_id", UNSET))

        def _parse_dataset_version_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                dataset_version_id_type_0 = UUID(data)

                return dataset_version_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        dataset_version_id = _parse_dataset_version_id(
            d.pop("dataset_version_id", UNSET)
        )

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

        job = cls(
            id=id,
            workspace_id=workspace_id,
            kind=kind,
            status=status,
            progress=progress,
            created_at=created_at,
            stage=stage,
            error_code=error_code,
            error_message=error_message,
            result=result,
            run_id=run_id,
            dataset_version_id=dataset_version_id,
            model_id=model_id,
            started_at=started_at,
            finished_at=finished_at,
        )

        job.additional_properties = d
        return job

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
