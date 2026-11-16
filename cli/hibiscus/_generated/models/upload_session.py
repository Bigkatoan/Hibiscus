from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.archive_format import ArchiveFormat
from ..models.upload_status import UploadStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.upload_part import UploadPart


T = TypeVar("T", bound="UploadSession")


@_attrs_define
class UploadSession:
    """
    Attributes:
        id (UUID):
        workspace_id (UUID):
        filename (str):
        size (int):
        sha256 (str):
        archive_format (ArchiveFormat): rar = RAR4/RAR5 via libarchive. Directories are tarred client-side by the CLI
            (format tar).
        part_size (int):
        part_count (int):
        parts (list[UploadPart]): Received parts, ascending part_number
        status (UploadStatus):
        expires_at (datetime.datetime):
        created_at (datetime.datetime):
        dataset_id (None | Unset | UUID):
        new_dataset_name (None | str | Unset):
        bytes_received (int | Unset):
        error_code (None | str | Unset):
        completed_at (datetime.datetime | None | Unset):
        dataset_version_id (None | Unset | UUID):
    """

    id: UUID
    workspace_id: UUID
    filename: str
    size: int
    sha256: str
    archive_format: ArchiveFormat
    part_size: int
    part_count: int
    parts: list[UploadPart]
    status: UploadStatus
    expires_at: datetime.datetime
    created_at: datetime.datetime
    dataset_id: None | Unset | UUID = UNSET
    new_dataset_name: None | str | Unset = UNSET
    bytes_received: int | Unset = UNSET
    error_code: None | str | Unset = UNSET
    completed_at: datetime.datetime | None | Unset = UNSET
    dataset_version_id: None | Unset | UUID = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        workspace_id = str(self.workspace_id)

        filename = self.filename

        size = self.size

        sha256 = self.sha256

        archive_format = self.archive_format.value

        part_size = self.part_size

        part_count = self.part_count

        parts = []
        for parts_item_data in self.parts:
            parts_item = parts_item_data.to_dict()
            parts.append(parts_item)

        status = self.status.value

        expires_at = self.expires_at.isoformat()

        created_at = self.created_at.isoformat()

        dataset_id: None | str | Unset
        if isinstance(self.dataset_id, Unset):
            dataset_id = UNSET
        elif isinstance(self.dataset_id, UUID):
            dataset_id = str(self.dataset_id)
        else:
            dataset_id = self.dataset_id

        new_dataset_name: None | str | Unset
        if isinstance(self.new_dataset_name, Unset):
            new_dataset_name = UNSET
        else:
            new_dataset_name = self.new_dataset_name

        bytes_received = self.bytes_received

        error_code: None | str | Unset
        if isinstance(self.error_code, Unset):
            error_code = UNSET
        else:
            error_code = self.error_code

        completed_at: None | str | Unset
        if isinstance(self.completed_at, Unset):
            completed_at = UNSET
        elif isinstance(self.completed_at, datetime.datetime):
            completed_at = self.completed_at.isoformat()
        else:
            completed_at = self.completed_at

        dataset_version_id: None | str | Unset
        if isinstance(self.dataset_version_id, Unset):
            dataset_version_id = UNSET
        elif isinstance(self.dataset_version_id, UUID):
            dataset_version_id = str(self.dataset_version_id)
        else:
            dataset_version_id = self.dataset_version_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "workspace_id": workspace_id,
                "filename": filename,
                "size": size,
                "sha256": sha256,
                "archive_format": archive_format,
                "part_size": part_size,
                "part_count": part_count,
                "parts": parts,
                "status": status,
                "expires_at": expires_at,
                "created_at": created_at,
            }
        )
        if dataset_id is not UNSET:
            field_dict["dataset_id"] = dataset_id
        if new_dataset_name is not UNSET:
            field_dict["new_dataset_name"] = new_dataset_name
        if bytes_received is not UNSET:
            field_dict["bytes_received"] = bytes_received
        if error_code is not UNSET:
            field_dict["error_code"] = error_code
        if completed_at is not UNSET:
            field_dict["completed_at"] = completed_at
        if dataset_version_id is not UNSET:
            field_dict["dataset_version_id"] = dataset_version_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.upload_part import UploadPart

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        workspace_id = UUID(d.pop("workspace_id"))

        filename = d.pop("filename")

        size = d.pop("size")

        sha256 = d.pop("sha256")

        archive_format = ArchiveFormat(d.pop("archive_format"))

        part_size = d.pop("part_size")

        part_count = d.pop("part_count")

        parts = []
        _parts = d.pop("parts")
        for parts_item_data in _parts:
            parts_item = UploadPart.from_dict(parts_item_data)

            parts.append(parts_item)

        status = UploadStatus(d.pop("status"))

        expires_at = isoparse(d.pop("expires_at"))

        created_at = isoparse(d.pop("created_at"))

        def _parse_dataset_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                dataset_id_type_0 = UUID(data)

                return dataset_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        dataset_id = _parse_dataset_id(d.pop("dataset_id", UNSET))

        def _parse_new_dataset_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        new_dataset_name = _parse_new_dataset_name(d.pop("new_dataset_name", UNSET))

        bytes_received = d.pop("bytes_received", UNSET)

        def _parse_error_code(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_code = _parse_error_code(d.pop("error_code", UNSET))

        def _parse_completed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                completed_at_type_0 = isoparse(data)

                return completed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        completed_at = _parse_completed_at(d.pop("completed_at", UNSET))

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

        upload_session = cls(
            id=id,
            workspace_id=workspace_id,
            filename=filename,
            size=size,
            sha256=sha256,
            archive_format=archive_format,
            part_size=part_size,
            part_count=part_count,
            parts=parts,
            status=status,
            expires_at=expires_at,
            created_at=created_at,
            dataset_id=dataset_id,
            new_dataset_name=new_dataset_name,
            bytes_received=bytes_received,
            error_code=error_code,
            completed_at=completed_at,
            dataset_version_id=dataset_version_id,
        )

        upload_session.additional_properties = d
        return upload_session

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
