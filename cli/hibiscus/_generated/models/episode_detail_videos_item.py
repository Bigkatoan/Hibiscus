from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="EpisodeDetailVideosItem")


@_attrs_define
class EpisodeDetailVideosItem:
    """
    Attributes:
        camera_key (str):
        media_path (str): e.g. videos/observation.images.wrist_cam/chunk-000/file-000.mp4
        from_timestamp_s (float): Seek offset inside the (concatenated v3.0) mp4
        to_timestamp_s (float):
        codec (str):
        width (int):
        height (int):
        browser_playable_hint (bool | Unset): False for codecs some browsers cannot decode (UI shows fallback)
        preview_media_path (None | str | Unset): Per-episode H.264 preview clip (<=480p, starts at t=0, no seek offset),
            e.g. previews/observation.images.wrist_cam/episode_000003.mp4; served via the same media endpoint. null until
            validation has generated it.
        thumbnail_media_path (None | str | Unset): JPEG thumbnail of the first frame, e.g.
            previews/observation.images.wrist_cam/episode_000003.jpg
    """

    camera_key: str
    media_path: str
    from_timestamp_s: float
    to_timestamp_s: float
    codec: str
    width: int
    height: int
    browser_playable_hint: bool | Unset = UNSET
    preview_media_path: None | str | Unset = UNSET
    thumbnail_media_path: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        camera_key = self.camera_key

        media_path = self.media_path

        from_timestamp_s = self.from_timestamp_s

        to_timestamp_s = self.to_timestamp_s

        codec = self.codec

        width = self.width

        height = self.height

        browser_playable_hint = self.browser_playable_hint

        preview_media_path: None | str | Unset
        if isinstance(self.preview_media_path, Unset):
            preview_media_path = UNSET
        else:
            preview_media_path = self.preview_media_path

        thumbnail_media_path: None | str | Unset
        if isinstance(self.thumbnail_media_path, Unset):
            thumbnail_media_path = UNSET
        else:
            thumbnail_media_path = self.thumbnail_media_path

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "camera_key": camera_key,
                "media_path": media_path,
                "from_timestamp_s": from_timestamp_s,
                "to_timestamp_s": to_timestamp_s,
                "codec": codec,
                "width": width,
                "height": height,
            }
        )
        if browser_playable_hint is not UNSET:
            field_dict["browser_playable_hint"] = browser_playable_hint
        if preview_media_path is not UNSET:
            field_dict["preview_media_path"] = preview_media_path
        if thumbnail_media_path is not UNSET:
            field_dict["thumbnail_media_path"] = thumbnail_media_path

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        camera_key = d.pop("camera_key")

        media_path = d.pop("media_path")

        from_timestamp_s = d.pop("from_timestamp_s")

        to_timestamp_s = d.pop("to_timestamp_s")

        codec = d.pop("codec")

        width = d.pop("width")

        height = d.pop("height")

        browser_playable_hint = d.pop("browser_playable_hint", UNSET)

        def _parse_preview_media_path(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        preview_media_path = _parse_preview_media_path(
            d.pop("preview_media_path", UNSET)
        )

        def _parse_thumbnail_media_path(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        thumbnail_media_path = _parse_thumbnail_media_path(
            d.pop("thumbnail_media_path", UNSET)
        )

        episode_detail_videos_item = cls(
            camera_key=camera_key,
            media_path=media_path,
            from_timestamp_s=from_timestamp_s,
            to_timestamp_s=to_timestamp_s,
            codec=codec,
            width=width,
            height=height,
            browser_playable_hint=browser_playable_hint,
            preview_media_path=preview_media_path,
            thumbnail_media_path=thumbnail_media_path,
        )

        episode_detail_videos_item.additional_properties = d
        return episode_detail_videos_item

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
