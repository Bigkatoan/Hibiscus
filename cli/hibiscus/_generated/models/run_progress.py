from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="RunProgress")


@_attrs_define
class RunProgress:
    """
    Attributes:
        current_step (int):
        total_steps (int):
        steps_per_s (Union[None, Unset, float]):
        eta_s (Union[None, Unset, float]):
        next_checkpoint_step (Union[None, Unset, int]): Next multiple of save_freq (or total_steps)
        last_checkpoint_step (Union[None, Unset, int]):
    """

    current_step: int
    total_steps: int
    steps_per_s: Union[None, Unset, float] = UNSET
    eta_s: Union[None, Unset, float] = UNSET
    next_checkpoint_step: Union[None, Unset, int] = UNSET
    last_checkpoint_step: Union[None, Unset, int] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        current_step = self.current_step

        total_steps = self.total_steps

        steps_per_s: Union[None, Unset, float]
        if isinstance(self.steps_per_s, Unset):
            steps_per_s = UNSET
        else:
            steps_per_s = self.steps_per_s

        eta_s: Union[None, Unset, float]
        if isinstance(self.eta_s, Unset):
            eta_s = UNSET
        else:
            eta_s = self.eta_s

        next_checkpoint_step: Union[None, Unset, int]
        if isinstance(self.next_checkpoint_step, Unset):
            next_checkpoint_step = UNSET
        else:
            next_checkpoint_step = self.next_checkpoint_step

        last_checkpoint_step: Union[None, Unset, int]
        if isinstance(self.last_checkpoint_step, Unset):
            last_checkpoint_step = UNSET
        else:
            last_checkpoint_step = self.last_checkpoint_step

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "current_step": current_step,
                "total_steps": total_steps,
            }
        )
        if steps_per_s is not UNSET:
            field_dict["steps_per_s"] = steps_per_s
        if eta_s is not UNSET:
            field_dict["eta_s"] = eta_s
        if next_checkpoint_step is not UNSET:
            field_dict["next_checkpoint_step"] = next_checkpoint_step
        if last_checkpoint_step is not UNSET:
            field_dict["last_checkpoint_step"] = last_checkpoint_step

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        current_step = d.pop("current_step")

        total_steps = d.pop("total_steps")

        def _parse_steps_per_s(data: object) -> Union[None, Unset, float]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, float], data)

        steps_per_s = _parse_steps_per_s(d.pop("steps_per_s", UNSET))

        def _parse_eta_s(data: object) -> Union[None, Unset, float]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, float], data)

        eta_s = _parse_eta_s(d.pop("eta_s", UNSET))

        def _parse_next_checkpoint_step(data: object) -> Union[None, Unset, int]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, int], data)

        next_checkpoint_step = _parse_next_checkpoint_step(
            d.pop("next_checkpoint_step", UNSET)
        )

        def _parse_last_checkpoint_step(data: object) -> Union[None, Unset, int]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, int], data)

        last_checkpoint_step = _parse_last_checkpoint_step(
            d.pop("last_checkpoint_step", UNSET)
        )

        run_progress = cls(
            current_step=current_step,
            total_steps=total_steps,
            steps_per_s=steps_per_s,
            eta_s=eta_s,
            next_checkpoint_step=next_checkpoint_step,
            last_checkpoint_step=last_checkpoint_step,
        )

        run_progress.additional_properties = d
        return run_progress

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
