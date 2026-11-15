from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    Union,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.preset_id import PresetId
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.preset_policy import PresetPolicy
    from ..models.preset_train import PresetTrain


T = TypeVar("T", bound="Preset")


@_attrs_define
class Preset:
    """
    Attributes:
        id (PresetId):
        label_key (str):
        train (PresetTrain): Partial train options
        policy (PresetPolicy): Partial policy options
        requires_init_from (Union[Unset, bool]):
    """

    id: PresetId
    label_key: str
    train: "PresetTrain"
    policy: "PresetPolicy"
    requires_init_from: Union[Unset, bool] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id.value

        label_key = self.label_key

        train = self.train.to_dict()

        policy = self.policy.to_dict()

        requires_init_from = self.requires_init_from

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "label_key": label_key,
                "train": train,
                "policy": policy,
            }
        )
        if requires_init_from is not UNSET:
            field_dict["requires_init_from"] = requires_init_from

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.preset_policy import PresetPolicy
        from ..models.preset_train import PresetTrain

        d = dict(src_dict)
        id = PresetId(d.pop("id"))

        label_key = d.pop("label_key")

        train = PresetTrain.from_dict(d.pop("train"))

        policy = PresetPolicy.from_dict(d.pop("policy"))

        requires_init_from = d.pop("requires_init_from", UNSET)

        preset = cls(
            id=id,
            label_key=label_key,
            train=train,
            policy=policy,
            requires_init_from=requires_init_from,
        )

        preset.additional_properties = d
        return preset

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
