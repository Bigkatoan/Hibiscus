from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="HubPushRequest")


@_attrs_define
class HubPushRequest:
    """
    Attributes:
        repo_id (str):
        private (bool | Unset):  Default: True.
        include_onnx (bool | Unset):  Default: False.
    """

    repo_id: str
    private: bool | Unset = True
    include_onnx: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        repo_id = self.repo_id

        private = self.private

        include_onnx = self.include_onnx

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "repo_id": repo_id,
            }
        )
        if private is not UNSET:
            field_dict["private"] = private
        if include_onnx is not UNSET:
            field_dict["include_onnx"] = include_onnx

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        repo_id = d.pop("repo_id")

        private = d.pop("private", UNSET)

        include_onnx = d.pop("include_onnx", UNSET)

        hub_push_request = cls(
            repo_id=repo_id,
            private=private,
            include_onnx=include_onnx,
        )

        return hub_push_request
