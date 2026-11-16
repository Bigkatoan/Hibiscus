from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.me_auth_method import MeAuthMethod
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.api_token import ApiToken
    from ..models.membership import Membership
    from ..models.user import User


T = TypeVar("T", bound="Me")


@_attrs_define
class Me:
    """
    Attributes:
        user (User):
        memberships (list[Membership]):
        auth_method (MeAuthMethod):
        mfa_verified (bool):
        mfa_enrollment_required (bool):
        session_id (None | Unset | UUID):
        token (ApiToken | None | Unset): Present when auth_method=pat
    """

    user: User
    memberships: list[Membership]
    auth_method: MeAuthMethod
    mfa_verified: bool
    mfa_enrollment_required: bool
    session_id: None | Unset | UUID = UNSET
    token: ApiToken | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.api_token import ApiToken

        user = self.user.to_dict()

        memberships = []
        for memberships_item_data in self.memberships:
            memberships_item = memberships_item_data.to_dict()
            memberships.append(memberships_item)

        auth_method = self.auth_method.value

        mfa_verified = self.mfa_verified

        mfa_enrollment_required = self.mfa_enrollment_required

        session_id: None | str | Unset
        if isinstance(self.session_id, Unset):
            session_id = UNSET
        elif isinstance(self.session_id, UUID):
            session_id = str(self.session_id)
        else:
            session_id = self.session_id

        token: dict[str, Any] | None | Unset
        if isinstance(self.token, Unset):
            token = UNSET
        elif isinstance(self.token, ApiToken):
            token = self.token.to_dict()
        else:
            token = self.token

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "user": user,
                "memberships": memberships,
                "auth_method": auth_method,
                "mfa_verified": mfa_verified,
                "mfa_enrollment_required": mfa_enrollment_required,
            }
        )
        if session_id is not UNSET:
            field_dict["session_id"] = session_id
        if token is not UNSET:
            field_dict["token"] = token

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.api_token import ApiToken
        from ..models.membership import Membership
        from ..models.user import User

        d = dict(src_dict)
        user = User.from_dict(d.pop("user"))

        memberships = []
        _memberships = d.pop("memberships")
        for memberships_item_data in _memberships:
            memberships_item = Membership.from_dict(memberships_item_data)

            memberships.append(memberships_item)

        auth_method = MeAuthMethod(d.pop("auth_method"))

        mfa_verified = d.pop("mfa_verified")

        mfa_enrollment_required = d.pop("mfa_enrollment_required")

        def _parse_session_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                session_id_type_0 = UUID(data)

                return session_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        session_id = _parse_session_id(d.pop("session_id", UNSET))

        def _parse_token(data: object) -> ApiToken | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                token_type_0 = ApiToken.from_dict(data)

                return token_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ApiToken | None | Unset, data)

        token = _parse_token(d.pop("token", UNSET))

        me = cls(
            user=user,
            memberships=memberships,
            auth_method=auth_method,
            mfa_verified=mfa_verified,
            mfa_enrollment_required=mfa_enrollment_required,
            session_id=session_id,
            token=token,
        )

        me.additional_properties = d
        return me

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
