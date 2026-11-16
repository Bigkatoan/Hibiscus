from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.dataset_version_summary import DatasetVersionSummary
    from ..models.user_ref import UserRef


T = TypeVar("T", bound="Dataset")


@_attrs_define
class Dataset:
    """
    Attributes:
        id (UUID):
        workspace_id (UUID):
        name (str):
        slug (str): Derived from name; used as `repo_id` suffix `local/<slug>`
        description (str):
        version_count (int):
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        created_by (UserRef | Unset):
        latest_version (DatasetVersionSummary | None | Unset):
    """

    id: UUID
    workspace_id: UUID
    name: str
    slug: str
    description: str
    version_count: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
    created_by: UserRef | Unset = UNSET
    latest_version: DatasetVersionSummary | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.dataset_version_summary import DatasetVersionSummary

        id = str(self.id)

        workspace_id = str(self.workspace_id)

        name = self.name

        slug = self.slug

        description = self.description

        version_count = self.version_count

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        created_by: dict[str, Any] | Unset = UNSET
        if not isinstance(self.created_by, Unset):
            created_by = self.created_by.to_dict()

        latest_version: dict[str, Any] | None | Unset
        if isinstance(self.latest_version, Unset):
            latest_version = UNSET
        elif isinstance(self.latest_version, DatasetVersionSummary):
            latest_version = self.latest_version.to_dict()
        else:
            latest_version = self.latest_version

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "workspace_id": workspace_id,
                "name": name,
                "slug": slug,
                "description": description,
                "version_count": version_count,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
        if created_by is not UNSET:
            field_dict["created_by"] = created_by
        if latest_version is not UNSET:
            field_dict["latest_version"] = latest_version

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.dataset_version_summary import DatasetVersionSummary
        from ..models.user_ref import UserRef

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        workspace_id = UUID(d.pop("workspace_id"))

        name = d.pop("name")

        slug = d.pop("slug")

        description = d.pop("description")

        version_count = d.pop("version_count")

        created_at = isoparse(d.pop("created_at"))

        updated_at = isoparse(d.pop("updated_at"))

        _created_by = d.pop("created_by", UNSET)
        created_by: UserRef | Unset
        if isinstance(_created_by, Unset):
            created_by = UNSET
        else:
            created_by = UserRef.from_dict(_created_by)

        def _parse_latest_version(data: object) -> DatasetVersionSummary | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                latest_version_type_0 = DatasetVersionSummary.from_dict(data)

                return latest_version_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DatasetVersionSummary | None | Unset, data)

        latest_version = _parse_latest_version(d.pop("latest_version", UNSET))

        dataset = cls(
            id=id,
            workspace_id=workspace_id,
            name=name,
            slug=slug,
            description=description,
            version_count=version_count,
            created_at=created_at,
            updated_at=updated_at,
            created_by=created_by,
            latest_version=latest_version,
        )

        dataset.additional_properties = d
        return dataset

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
