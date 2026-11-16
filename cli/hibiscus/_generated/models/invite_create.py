from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..models.invite_create_role import InviteCreateRole

T = TypeVar("T", bound="InviteCreate")


@_attrs_define
class InviteCreate:
    """
    Attributes:
        email (str):
        role (InviteCreateRole):
    """

    email: str
    role: InviteCreateRole

    def to_dict(self) -> dict[str, Any]:
        email = self.email

        role = self.role.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "email": email,
                "role": role,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        email = d.pop("email")

        role = InviteCreateRole(d.pop("role"))

        invite_create = cls(
            email=email,
            role=role,
        )

        return invite_create
