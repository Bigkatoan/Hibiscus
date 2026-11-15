import datetime
from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
    cast,
)
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.policy_type import PolicyType
from ..types import UNSET, Unset

T = TypeVar("T", bound="QueueEntry")


@_attrs_define
class QueueEntry:
    """
    Attributes:
        position (int):
        policy_type (PolicyType):
        requested_gpu (str):
        queued_at (datetime.datetime):
        run_id (Union[None, UUID, Unset]): null for other workspaces
        run_name (Union[None, Unset, str]):
        workspace_id (Union[None, UUID, Unset]):
        required_vram_mb (Union[None, Unset, int]):
        estimated_start_at (Union[None, Unset, datetime.datetime]):
    """

    position: int
    policy_type: PolicyType
    requested_gpu: str
    queued_at: datetime.datetime
    run_id: Union[None, UUID, Unset] = UNSET
    run_name: Union[None, Unset, str] = UNSET
    workspace_id: Union[None, UUID, Unset] = UNSET
    required_vram_mb: Union[None, Unset, int] = UNSET
    estimated_start_at: Union[None, Unset, datetime.datetime] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        position = self.position

        policy_type = self.policy_type.value

        requested_gpu = self.requested_gpu

        queued_at = self.queued_at.isoformat()

        run_id: Union[None, Unset, str]
        if isinstance(self.run_id, Unset):
            run_id = UNSET
        elif isinstance(self.run_id, UUID):
            run_id = str(self.run_id)
        else:
            run_id = self.run_id

        run_name: Union[None, Unset, str]
        if isinstance(self.run_name, Unset):
            run_name = UNSET
        else:
            run_name = self.run_name

        workspace_id: Union[None, Unset, str]
        if isinstance(self.workspace_id, Unset):
            workspace_id = UNSET
        elif isinstance(self.workspace_id, UUID):
            workspace_id = str(self.workspace_id)
        else:
            workspace_id = self.workspace_id

        required_vram_mb: Union[None, Unset, int]
        if isinstance(self.required_vram_mb, Unset):
            required_vram_mb = UNSET
        else:
            required_vram_mb = self.required_vram_mb

        estimated_start_at: Union[None, Unset, str]
        if isinstance(self.estimated_start_at, Unset):
            estimated_start_at = UNSET
        elif isinstance(self.estimated_start_at, datetime.datetime):
            estimated_start_at = self.estimated_start_at.isoformat()
        else:
            estimated_start_at = self.estimated_start_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "position": position,
                "policy_type": policy_type,
                "requested_gpu": requested_gpu,
                "queued_at": queued_at,
            }
        )
        if run_id is not UNSET:
            field_dict["run_id"] = run_id
        if run_name is not UNSET:
            field_dict["run_name"] = run_name
        if workspace_id is not UNSET:
            field_dict["workspace_id"] = workspace_id
        if required_vram_mb is not UNSET:
            field_dict["required_vram_mb"] = required_vram_mb
        if estimated_start_at is not UNSET:
            field_dict["estimated_start_at"] = estimated_start_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        position = d.pop("position")

        policy_type = PolicyType(d.pop("policy_type"))

        requested_gpu = d.pop("requested_gpu")

        queued_at = isoparse(d.pop("queued_at"))

        def _parse_run_id(data: object) -> Union[None, UUID, Unset]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                run_id_type_0 = UUID(data)

                return run_id_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, UUID, Unset], data)

        run_id = _parse_run_id(d.pop("run_id", UNSET))

        def _parse_run_name(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        run_name = _parse_run_name(d.pop("run_name", UNSET))

        def _parse_workspace_id(data: object) -> Union[None, UUID, Unset]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                workspace_id_type_0 = UUID(data)

                return workspace_id_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, UUID, Unset], data)

        workspace_id = _parse_workspace_id(d.pop("workspace_id", UNSET))

        def _parse_required_vram_mb(data: object) -> Union[None, Unset, int]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, int], data)

        required_vram_mb = _parse_required_vram_mb(d.pop("required_vram_mb", UNSET))

        def _parse_estimated_start_at(
            data: object,
        ) -> Union[None, Unset, datetime.datetime]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                estimated_start_at_type_0 = isoparse(data)

                return estimated_start_at_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, datetime.datetime], data)

        estimated_start_at = _parse_estimated_start_at(
            d.pop("estimated_start_at", UNSET)
        )

        queue_entry = cls(
            position=position,
            policy_type=policy_type,
            requested_gpu=requested_gpu,
            queued_at=queued_at,
            run_id=run_id,
            run_name=run_name,
            workspace_id=workspace_id,
            required_vram_mb=required_vram_mb,
            estimated_start_at=estimated_start_at,
        )

        queue_entry.additional_properties = d
        return queue_entry

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
