from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.onnx_support import OnnxSupport
from ..models.policy_type import PolicyType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.policy_summary_gpu_support import PolicySummaryGpuSupport


T = TypeVar("T", bound="PolicySummary")


@_attrs_define
class PolicySummary:
    """
    Attributes:
        type_ (PolicyType):
        display_name (str):
        trainable (bool):
        onnx (OnnxSupport): full: single graph; split: encoder + denoiser graphs, loop in infer_onnx.py; none: no ONNX
            in v1
        requires_peft (bool): pi0/pi05: only LoRA/PEFT fine-tuning allowed
        requires_reward (bool): tdmpc: dataset must contain next.reward
        gpu_support (PolicySummaryGpuSupport): gpu name -> support level
        schema_etag (str):
        onnx_reason_key (None | str | Unset): i18n key explaining missing ONNX
        requires_language (bool | Unset): smolvla/pi0/pi05 use the task string
        experimental (bool | Unset):
    """

    type_: PolicyType
    display_name: str
    trainable: bool
    onnx: OnnxSupport
    requires_peft: bool
    requires_reward: bool
    gpu_support: PolicySummaryGpuSupport
    schema_etag: str
    onnx_reason_key: None | str | Unset = UNSET
    requires_language: bool | Unset = UNSET
    experimental: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_.value

        display_name = self.display_name

        trainable = self.trainable

        onnx = self.onnx.value

        requires_peft = self.requires_peft

        requires_reward = self.requires_reward

        gpu_support = self.gpu_support.to_dict()

        schema_etag = self.schema_etag

        onnx_reason_key: None | str | Unset
        if isinstance(self.onnx_reason_key, Unset):
            onnx_reason_key = UNSET
        else:
            onnx_reason_key = self.onnx_reason_key

        requires_language = self.requires_language

        experimental = self.experimental

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "display_name": display_name,
                "trainable": trainable,
                "onnx": onnx,
                "requires_peft": requires_peft,
                "requires_reward": requires_reward,
                "gpu_support": gpu_support,
                "schema_etag": schema_etag,
            }
        )
        if onnx_reason_key is not UNSET:
            field_dict["onnx_reason_key"] = onnx_reason_key
        if requires_language is not UNSET:
            field_dict["requires_language"] = requires_language
        if experimental is not UNSET:
            field_dict["experimental"] = experimental

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.policy_summary_gpu_support import PolicySummaryGpuSupport

        d = dict(src_dict)
        type_ = PolicyType(d.pop("type"))

        display_name = d.pop("display_name")

        trainable = d.pop("trainable")

        onnx = OnnxSupport(d.pop("onnx"))

        requires_peft = d.pop("requires_peft")

        requires_reward = d.pop("requires_reward")

        gpu_support = PolicySummaryGpuSupport.from_dict(d.pop("gpu_support"))

        schema_etag = d.pop("schema_etag")

        def _parse_onnx_reason_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        onnx_reason_key = _parse_onnx_reason_key(d.pop("onnx_reason_key", UNSET))

        requires_language = d.pop("requires_language", UNSET)

        experimental = d.pop("experimental", UNSET)

        policy_summary = cls(
            type_=type_,
            display_name=display_name,
            trainable=trainable,
            onnx=onnx,
            requires_peft=requires_peft,
            requires_reward=requires_reward,
            gpu_support=gpu_support,
            schema_etag=schema_etag,
            onnx_reason_key=onnx_reason_key,
            requires_language=requires_language,
            experimental=experimental,
        )

        policy_summary.additional_properties = d
        return policy_summary

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
