from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.dataset_preview_length_histogram import DatasetPreviewLengthHistogram
    from ..models.episode_summary import EpisodeSummary


T = TypeVar("T", bound="DatasetPreview")


@_attrs_define
class DatasetPreview:
    """
    Attributes:
        dataset_version_id (UUID):
        fps (float):
        camera_keys (list[str]):
        episodes (list[EpisodeSummary]):
        length_histogram (DatasetPreviewLengthHistogram):
    """

    dataset_version_id: UUID
    fps: float
    camera_keys: list[str]
    episodes: list[EpisodeSummary]
    length_histogram: DatasetPreviewLengthHistogram
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        dataset_version_id = str(self.dataset_version_id)

        fps = self.fps

        camera_keys = self.camera_keys

        episodes = []
        for episodes_item_data in self.episodes:
            episodes_item = episodes_item_data.to_dict()
            episodes.append(episodes_item)

        length_histogram = self.length_histogram.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "dataset_version_id": dataset_version_id,
                "fps": fps,
                "camera_keys": camera_keys,
                "episodes": episodes,
                "length_histogram": length_histogram,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.dataset_preview_length_histogram import (
            DatasetPreviewLengthHistogram,
        )
        from ..models.episode_summary import EpisodeSummary

        d = dict(src_dict)
        dataset_version_id = UUID(d.pop("dataset_version_id"))

        fps = d.pop("fps")

        camera_keys = cast(list[str], d.pop("camera_keys"))

        episodes = []
        _episodes = d.pop("episodes")
        for episodes_item_data in _episodes:
            episodes_item = EpisodeSummary.from_dict(episodes_item_data)

            episodes.append(episodes_item)

        length_histogram = DatasetPreviewLengthHistogram.from_dict(
            d.pop("length_histogram")
        )

        dataset_preview = cls(
            dataset_version_id=dataset_version_id,
            fps=fps,
            camera_keys=camera_keys,
            episodes=episodes,
            length_histogram=length_histogram,
        )

        dataset_preview.additional_properties = d
        return dataset_preview

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
