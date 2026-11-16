from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.episode_detail_series_item import EpisodeDetailSeriesItem
    from ..models.episode_detail_videos_item import EpisodeDetailVideosItem


T = TypeVar("T", bound="EpisodeDetail")


@_attrs_define
class EpisodeDetail:
    """
    Attributes:
        index (int):
        length (int):
        fps (float):
        timestamps (list[float]): Seconds from episode start, downsampled (shared x-axis)
        series (list[EpisodeDetailSeriesItem]): One per feature dimension (observation.state[i], action[i])
        videos (list[EpisodeDetailVideosItem]):
    """

    index: int
    length: int
    fps: float
    timestamps: list[float]
    series: list[EpisodeDetailSeriesItem]
    videos: list[EpisodeDetailVideosItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        index = self.index

        length = self.length

        fps = self.fps

        timestamps = self.timestamps

        series = []
        for series_item_data in self.series:
            series_item = series_item_data.to_dict()
            series.append(series_item)

        videos = []
        for videos_item_data in self.videos:
            videos_item = videos_item_data.to_dict()
            videos.append(videos_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "index": index,
                "length": length,
                "fps": fps,
                "timestamps": timestamps,
                "series": series,
                "videos": videos,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.episode_detail_series_item import EpisodeDetailSeriesItem
        from ..models.episode_detail_videos_item import EpisodeDetailVideosItem

        d = dict(src_dict)
        index = d.pop("index")

        length = d.pop("length")

        fps = d.pop("fps")

        timestamps = cast(list[float], d.pop("timestamps"))

        series = []
        _series = d.pop("series")
        for series_item_data in _series:
            series_item = EpisodeDetailSeriesItem.from_dict(series_item_data)

            series.append(series_item)

        videos = []
        _videos = d.pop("videos")
        for videos_item_data in _videos:
            videos_item = EpisodeDetailVideosItem.from_dict(videos_item_data)

            videos.append(videos_item)

        episode_detail = cls(
            index=index,
            length=length,
            fps=fps,
            timestamps=timestamps,
            series=series,
            videos=videos,
        )

        episode_detail.additional_properties = d
        return episode_detail

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
