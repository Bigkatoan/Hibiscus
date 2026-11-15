from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    Union,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.episode_summary_thumbnails import EpisodeSummaryThumbnails


T = TypeVar("T", bound="EpisodeSummary")


@_attrs_define
class EpisodeSummary:
    """
    Attributes:
        index (int):
        length (int): Frames
        duration_s (float):
        tasks (list[str]):
        thumbnails (EpisodeSummaryThumbnails): camera key -> media path (use with getDatasetMedia)
        has_issues (Union[Unset, bool]):
    """

    index: int
    length: int
    duration_s: float
    tasks: list[str]
    thumbnails: "EpisodeSummaryThumbnails"
    has_issues: Union[Unset, bool] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        index = self.index

        length = self.length

        duration_s = self.duration_s

        tasks = self.tasks

        thumbnails = self.thumbnails.to_dict()

        has_issues = self.has_issues

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "index": index,
                "length": length,
                "duration_s": duration_s,
                "tasks": tasks,
                "thumbnails": thumbnails,
            }
        )
        if has_issues is not UNSET:
            field_dict["has_issues"] = has_issues

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.episode_summary_thumbnails import EpisodeSummaryThumbnails

        d = dict(src_dict)
        index = d.pop("index")

        length = d.pop("length")

        duration_s = d.pop("duration_s")

        tasks = cast(list[str], d.pop("tasks"))

        thumbnails = EpisodeSummaryThumbnails.from_dict(d.pop("thumbnails"))

        has_issues = d.pop("has_issues", UNSET)

        episode_summary = cls(
            index=index,
            length=length,
            duration_s=duration_s,
            tasks=tasks,
            thumbnails=thumbnails,
            has_issues=has_issues,
        )

        episode_summary.additional_properties = d
        return episode_summary

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
