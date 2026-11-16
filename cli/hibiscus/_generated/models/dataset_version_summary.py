from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.dataset_source import DatasetSource
from ..models.dataset_version_status import DatasetVersionStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="DatasetVersionSummary")


@_attrs_define
class DatasetVersionSummary:
    """
    Attributes:
        id (UUID):
        dataset_id (UUID):
        version (int):
        status (DatasetVersionStatus):
        source (DatasetSource):
        created_at (datetime.datetime):
        total_episodes (int | None | Unset):
        total_frames (int | None | Unset):
        fps (float | None | Unset):
        size_bytes (int | None | Unset):
    """

    id: UUID
    dataset_id: UUID
    version: int
    status: DatasetVersionStatus
    source: DatasetSource
    created_at: datetime.datetime
    total_episodes: int | None | Unset = UNSET
    total_frames: int | None | Unset = UNSET
    fps: float | None | Unset = UNSET
    size_bytes: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        dataset_id = str(self.dataset_id)

        version = self.version

        status = self.status.value

        source = self.source.value

        created_at = self.created_at.isoformat()

        total_episodes: int | None | Unset
        if isinstance(self.total_episodes, Unset):
            total_episodes = UNSET
        else:
            total_episodes = self.total_episodes

        total_frames: int | None | Unset
        if isinstance(self.total_frames, Unset):
            total_frames = UNSET
        else:
            total_frames = self.total_frames

        fps: float | None | Unset
        if isinstance(self.fps, Unset):
            fps = UNSET
        else:
            fps = self.fps

        size_bytes: int | None | Unset
        if isinstance(self.size_bytes, Unset):
            size_bytes = UNSET
        else:
            size_bytes = self.size_bytes

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "dataset_id": dataset_id,
                "version": version,
                "status": status,
                "source": source,
                "created_at": created_at,
            }
        )
        if total_episodes is not UNSET:
            field_dict["total_episodes"] = total_episodes
        if total_frames is not UNSET:
            field_dict["total_frames"] = total_frames
        if fps is not UNSET:
            field_dict["fps"] = fps
        if size_bytes is not UNSET:
            field_dict["size_bytes"] = size_bytes

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        dataset_id = UUID(d.pop("dataset_id"))

        version = d.pop("version")

        status = DatasetVersionStatus(d.pop("status"))

        source = DatasetSource(d.pop("source"))

        created_at = isoparse(d.pop("created_at"))

        def _parse_total_episodes(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        total_episodes = _parse_total_episodes(d.pop("total_episodes", UNSET))

        def _parse_total_frames(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        total_frames = _parse_total_frames(d.pop("total_frames", UNSET))

        def _parse_fps(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        fps = _parse_fps(d.pop("fps", UNSET))

        def _parse_size_bytes(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        size_bytes = _parse_size_bytes(d.pop("size_bytes", UNSET))

        dataset_version_summary = cls(
            id=id,
            dataset_id=dataset_id,
            version=version,
            status=status,
            source=source,
            created_at=created_at,
            total_episodes=total_episodes,
            total_frames=total_frames,
            fps=fps,
            size_bytes=size_bytes,
        )

        dataset_version_summary.additional_properties = d
        return dataset_version_summary

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
