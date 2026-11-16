from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="RunManifestDataset")


@_attrs_define
class RunManifestDataset:
    """
    Attributes:
        dataset_id (UUID):
        version_id (UUID):
        version (int):
        content_hash (str):
        repo_id (str):
    """

    dataset_id: UUID
    version_id: UUID
    version: int
    content_hash: str
    repo_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        dataset_id = str(self.dataset_id)

        version_id = str(self.version_id)

        version = self.version

        content_hash = self.content_hash

        repo_id = self.repo_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "dataset_id": dataset_id,
                "version_id": version_id,
                "version": version,
                "content_hash": content_hash,
                "repo_id": repo_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        dataset_id = UUID(d.pop("dataset_id"))

        version_id = UUID(d.pop("version_id"))

        version = d.pop("version")

        content_hash = d.pop("content_hash")

        repo_id = d.pop("repo_id")

        run_manifest_dataset = cls(
            dataset_id=dataset_id,
            version_id=version_id,
            version=version,
            content_hash=content_hash,
            repo_id=repo_id,
        )

        run_manifest_dataset.additional_properties = d
        return run_manifest_dataset

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
