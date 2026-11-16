from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.mixed_precision import MixedPrecision

if TYPE_CHECKING:
    from ..models.run_config import RunConfig


T = TypeVar("T", bound="PreflightReportResolved")


@_attrs_define
class PreflightReportResolved:
    """
    Attributes:
        gpu_id (None | str): null when auto and decided at dispatch
        mixed_precision (MixedPrecision):
        config (RunConfig):
        heldout_episodes (list[int]):
        train_episodes (list[int]):
        lerobot_args (list[str]): argv preview (paths shown as placeholders)
    """

    gpu_id: None | str
    mixed_precision: MixedPrecision
    config: RunConfig
    heldout_episodes: list[int]
    train_episodes: list[int]
    lerobot_args: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        gpu_id: None | str
        gpu_id = self.gpu_id

        mixed_precision = self.mixed_precision.value

        config = self.config.to_dict()

        heldout_episodes = self.heldout_episodes

        train_episodes = self.train_episodes

        lerobot_args = self.lerobot_args

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "gpu_id": gpu_id,
                "mixed_precision": mixed_precision,
                "config": config,
                "heldout_episodes": heldout_episodes,
                "train_episodes": train_episodes,
                "lerobot_args": lerobot_args,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.run_config import RunConfig

        d = dict(src_dict)

        def _parse_gpu_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        gpu_id = _parse_gpu_id(d.pop("gpu_id"))

        mixed_precision = MixedPrecision(d.pop("mixed_precision"))

        config = RunConfig.from_dict(d.pop("config"))

        heldout_episodes = cast(list[int], d.pop("heldout_episodes"))

        train_episodes = cast(list[int], d.pop("train_episodes"))

        lerobot_args = cast(list[str], d.pop("lerobot_args"))

        preflight_report_resolved = cls(
            gpu_id=gpu_id,
            mixed_precision=mixed_precision,
            config=config,
            heldout_episodes=heldout_episodes,
            train_episodes=train_episodes,
            lerobot_args=lerobot_args,
        )

        preflight_report_resolved.additional_properties = d
        return preflight_report_resolved

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
