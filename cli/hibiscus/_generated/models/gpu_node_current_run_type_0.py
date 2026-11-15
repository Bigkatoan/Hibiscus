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

from ..types import UNSET, Unset

T = TypeVar("T", bound="GpuNodeCurrentRunType0")


@_attrs_define
class GpuNodeCurrentRunType0:
    """Null when idle; `id`/`name` null when the run is in another workspace

    Attributes:
        id (Union[None, UUID, Unset]):
        name (Union[None, Unset, str]):
        workspace_id (Union[None, UUID, Unset]):
        step (Union[Unset, int]):
        total_steps (Union[Unset, int]):
    """

    id: Union[None, UUID, Unset] = UNSET
    name: Union[None, Unset, str] = UNSET
    workspace_id: Union[None, UUID, Unset] = UNSET
    step: Union[Unset, int] = UNSET
    total_steps: Union[Unset, int] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id: Union[None, Unset, str]
        if isinstance(self.id, Unset):
            id = UNSET
        elif isinstance(self.id, UUID):
            id = str(self.id)
        else:
            id = self.id

        name: Union[None, Unset, str]
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        workspace_id: Union[None, Unset, str]
        if isinstance(self.workspace_id, Unset):
            workspace_id = UNSET
        elif isinstance(self.workspace_id, UUID):
            workspace_id = str(self.workspace_id)
        else:
            workspace_id = self.workspace_id

        step = self.step

        total_steps = self.total_steps

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if id is not UNSET:
            field_dict["id"] = id
        if name is not UNSET:
            field_dict["name"] = name
        if workspace_id is not UNSET:
            field_dict["workspace_id"] = workspace_id
        if step is not UNSET:
            field_dict["step"] = step
        if total_steps is not UNSET:
            field_dict["total_steps"] = total_steps

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_id(data: object) -> Union[None, UUID, Unset]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                id_type_0 = UUID(data)

                return id_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, UUID, Unset], data)

        id = _parse_id(d.pop("id", UNSET))

        def _parse_name(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        name = _parse_name(d.pop("name", UNSET))

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

        step = d.pop("step", UNSET)

        total_steps = d.pop("total_steps", UNSET)

        gpu_node_current_run_type_0 = cls(
            id=id,
            name=name,
            workspace_id=workspace_id,
            step=step,
            total_steps=total_steps,
        )

        gpu_node_current_run_type_0.additional_properties = d
        return gpu_node_current_run_type_0

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
