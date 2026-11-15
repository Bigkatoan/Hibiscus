from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.bundle_manifest_files_item import BundleManifestFilesItem


T = TypeVar("T", bound="BundleManifest")


@_attrs_define
class BundleManifest:
    """MANIFEST.json (normative JSON Schema in docs/spec/bundle.md §3; this mirrors it)

    Attributes:
        schema_version (Literal['1']):
        bundle_name (str):
        files (list['BundleManifestFilesItem']):
    """

    schema_version: Literal["1"]
    bundle_name: str
    files: list["BundleManifestFilesItem"]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        schema_version = self.schema_version

        bundle_name = self.bundle_name

        files = []
        for files_item_data in self.files:
            files_item = files_item_data.to_dict()
            files.append(files_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "schema_version": schema_version,
                "bundle_name": bundle_name,
                "files": files,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.bundle_manifest_files_item import BundleManifestFilesItem

        d = dict(src_dict)
        schema_version = cast(Literal["1"], d.pop("schema_version"))
        if schema_version != "1":
            raise ValueError(
                f"schema_version must match const '1', got '{schema_version}'"
            )

        bundle_name = d.pop("bundle_name")

        files = []
        _files = d.pop("files")
        for files_item_data in _files:
            files_item = BundleManifestFilesItem.from_dict(files_item_data)

            files.append(files_item)

        bundle_manifest = cls(
            schema_version=schema_version,
            bundle_name=bundle_name,
            files=files,
        )

        bundle_manifest.additional_properties = d
        return bundle_manifest

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
