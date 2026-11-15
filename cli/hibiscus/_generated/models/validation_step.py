import datetime
from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    Union,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.validation_step_id import ValidationStepId
from ..models.validation_step_status import ValidationStepStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.validation_issue import ValidationIssue


T = TypeVar("T", bound="ValidationStep")


@_attrs_define
class ValidationStep:
    """
    Attributes:
        id (ValidationStepId): Order is fixed (PLAN 3.2) - checksum and unpack precede the 5 validation steps.
        status (ValidationStepStatus):
        issues (list['ValidationIssue']):
        started_at (Union[None, Unset, datetime.datetime]):
        finished_at (Union[None, Unset, datetime.datetime]):
        progress (Union[Unset, float]):
        issues_truncated (Union[Unset, int]): Number of issues beyond the 500 kept
    """

    id: ValidationStepId
    status: ValidationStepStatus
    issues: list["ValidationIssue"]
    started_at: Union[None, Unset, datetime.datetime] = UNSET
    finished_at: Union[None, Unset, datetime.datetime] = UNSET
    progress: Union[Unset, float] = UNSET
    issues_truncated: Union[Unset, int] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id.value

        status = self.status.value

        issues = []
        for issues_item_data in self.issues:
            issues_item = issues_item_data.to_dict()
            issues.append(issues_item)

        started_at: Union[None, Unset, str]
        if isinstance(self.started_at, Unset):
            started_at = UNSET
        elif isinstance(self.started_at, datetime.datetime):
            started_at = self.started_at.isoformat()
        else:
            started_at = self.started_at

        finished_at: Union[None, Unset, str]
        if isinstance(self.finished_at, Unset):
            finished_at = UNSET
        elif isinstance(self.finished_at, datetime.datetime):
            finished_at = self.finished_at.isoformat()
        else:
            finished_at = self.finished_at

        progress = self.progress

        issues_truncated = self.issues_truncated

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "status": status,
                "issues": issues,
            }
        )
        if started_at is not UNSET:
            field_dict["started_at"] = started_at
        if finished_at is not UNSET:
            field_dict["finished_at"] = finished_at
        if progress is not UNSET:
            field_dict["progress"] = progress
        if issues_truncated is not UNSET:
            field_dict["issues_truncated"] = issues_truncated

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.validation_issue import ValidationIssue

        d = dict(src_dict)
        id = ValidationStepId(d.pop("id"))

        status = ValidationStepStatus(d.pop("status"))

        issues = []
        _issues = d.pop("issues")
        for issues_item_data in _issues:
            issues_item = ValidationIssue.from_dict(issues_item_data)

            issues.append(issues_item)

        def _parse_started_at(data: object) -> Union[None, Unset, datetime.datetime]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                started_at_type_0 = isoparse(data)

                return started_at_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, datetime.datetime], data)

        started_at = _parse_started_at(d.pop("started_at", UNSET))

        def _parse_finished_at(data: object) -> Union[None, Unset, datetime.datetime]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                finished_at_type_0 = isoparse(data)

                return finished_at_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, datetime.datetime], data)

        finished_at = _parse_finished_at(d.pop("finished_at", UNSET))

        progress = d.pop("progress", UNSET)

        issues_truncated = d.pop("issues_truncated", UNSET)

        validation_step = cls(
            id=id,
            status=status,
            issues=issues,
            started_at=started_at,
            finished_at=finished_at,
            progress=progress,
            issues_truncated=issues_truncated,
        )

        validation_step.additional_properties = d
        return validation_step

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
