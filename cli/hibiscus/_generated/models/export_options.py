from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ExportOptions")


@_attrs_define
class ExportOptions:
    """
    Attributes:
        onnx (bool | Unset): Ignored (onnx_status=not_supported) for policies with onnx=none Default: True.
        onnx_fp16 (bool | Unset):  Default: False.
        eval_ (bool | Unset): Run held-out offline eval and include eval/ in bundle Default: True.
        model_name (str | Unset): Default: dataset slug + policy type
    """

    onnx: bool | Unset = True
    onnx_fp16: bool | Unset = False
    eval_: bool | Unset = True
    model_name: str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        onnx = self.onnx

        onnx_fp16 = self.onnx_fp16

        eval_ = self.eval_

        model_name = self.model_name

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if onnx is not UNSET:
            field_dict["onnx"] = onnx
        if onnx_fp16 is not UNSET:
            field_dict["onnx_fp16"] = onnx_fp16
        if eval_ is not UNSET:
            field_dict["eval"] = eval_
        if model_name is not UNSET:
            field_dict["model_name"] = model_name

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        onnx = d.pop("onnx", UNSET)

        onnx_fp16 = d.pop("onnx_fp16", UNSET)

        eval_ = d.pop("eval", UNSET)

        model_name = d.pop("model_name", UNSET)

        export_options = cls(
            onnx=onnx,
            onnx_fp16=onnx_fp16,
            eval_=eval_,
            model_name=model_name,
        )

        return export_options
