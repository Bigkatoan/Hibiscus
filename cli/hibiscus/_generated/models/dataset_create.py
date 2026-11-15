from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
)
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="DatasetCreate")


@_attrs_define
class DatasetCreate:
    """
    Attributes:
        workspace_id (UUID):
        name (str):
        description (Union[Unset, str]):
    """

    workspace_id: UUID
    name: str
    description: Union[Unset, str] = UNSET

    def to_dict(self) -> dict[str, Any]:
        workspace_id = str(self.workspace_id)

        name = self.name

        description = self.description

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "workspace_id": workspace_id,
                "name": name,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        workspace_id = UUID(d.pop("workspace_id"))

        name = d.pop("name")

        description = d.pop("description", UNSET)

        dataset_create = cls(
            workspace_id=workspace_id,
            name=name,
            description=description,
        )

        return dataset_create
