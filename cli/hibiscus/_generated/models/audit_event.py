from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.audit_action import AuditAction
from ..models.audit_event_outcome import AuditEventOutcome
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.audit_event_details import AuditEventDetails
    from ..models.user_ref import UserRef


T = TypeVar("T", bound="AuditEvent")


@_attrs_define
class AuditEvent:
    """
    Attributes:
        id (int):
        created_at (datetime.datetime):
        action (AuditAction): Catalogue in docs/db-schema.md §Audit
        outcome (AuditEventOutcome):
        workspace_id (None | Unset | UUID):
        actor (None | Unset | UserRef):
        actor_token_id (None | Unset | UUID):
        target_type (None | str | Unset):
        target_id (None | str | Unset):
        ip (None | str | Unset):
        user_agent (None | str | Unset):
        request_id (None | str | Unset):
        details (AuditEventDetails | Unset):
    """

    id: int
    created_at: datetime.datetime
    action: AuditAction
    outcome: AuditEventOutcome
    workspace_id: None | Unset | UUID = UNSET
    actor: None | Unset | UserRef = UNSET
    actor_token_id: None | Unset | UUID = UNSET
    target_type: None | str | Unset = UNSET
    target_id: None | str | Unset = UNSET
    ip: None | str | Unset = UNSET
    user_agent: None | str | Unset = UNSET
    request_id: None | str | Unset = UNSET
    details: AuditEventDetails | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.user_ref import UserRef

        id = self.id

        created_at = self.created_at.isoformat()

        action = self.action.value

        outcome = self.outcome.value

        workspace_id: None | str | Unset
        if isinstance(self.workspace_id, Unset):
            workspace_id = UNSET
        elif isinstance(self.workspace_id, UUID):
            workspace_id = str(self.workspace_id)
        else:
            workspace_id = self.workspace_id

        actor: dict[str, Any] | None | Unset
        if isinstance(self.actor, Unset):
            actor = UNSET
        elif isinstance(self.actor, UserRef):
            actor = self.actor.to_dict()
        else:
            actor = self.actor

        actor_token_id: None | str | Unset
        if isinstance(self.actor_token_id, Unset):
            actor_token_id = UNSET
        elif isinstance(self.actor_token_id, UUID):
            actor_token_id = str(self.actor_token_id)
        else:
            actor_token_id = self.actor_token_id

        target_type: None | str | Unset
        if isinstance(self.target_type, Unset):
            target_type = UNSET
        else:
            target_type = self.target_type

        target_id: None | str | Unset
        if isinstance(self.target_id, Unset):
            target_id = UNSET
        else:
            target_id = self.target_id

        ip: None | str | Unset
        if isinstance(self.ip, Unset):
            ip = UNSET
        else:
            ip = self.ip

        user_agent: None | str | Unset
        if isinstance(self.user_agent, Unset):
            user_agent = UNSET
        else:
            user_agent = self.user_agent

        request_id: None | str | Unset
        if isinstance(self.request_id, Unset):
            request_id = UNSET
        else:
            request_id = self.request_id

        details: dict[str, Any] | Unset = UNSET
        if not isinstance(self.details, Unset):
            details = self.details.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "created_at": created_at,
                "action": action,
                "outcome": outcome,
            }
        )
        if workspace_id is not UNSET:
            field_dict["workspace_id"] = workspace_id
        if actor is not UNSET:
            field_dict["actor"] = actor
        if actor_token_id is not UNSET:
            field_dict["actor_token_id"] = actor_token_id
        if target_type is not UNSET:
            field_dict["target_type"] = target_type
        if target_id is not UNSET:
            field_dict["target_id"] = target_id
        if ip is not UNSET:
            field_dict["ip"] = ip
        if user_agent is not UNSET:
            field_dict["user_agent"] = user_agent
        if request_id is not UNSET:
            field_dict["request_id"] = request_id
        if details is not UNSET:
            field_dict["details"] = details

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.audit_event_details import AuditEventDetails
        from ..models.user_ref import UserRef

        d = dict(src_dict)
        id = d.pop("id")

        created_at = isoparse(d.pop("created_at"))

        action = AuditAction(d.pop("action"))

        outcome = AuditEventOutcome(d.pop("outcome"))

        def _parse_workspace_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                workspace_id_type_0 = UUID(data)

                return workspace_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        workspace_id = _parse_workspace_id(d.pop("workspace_id", UNSET))

        def _parse_actor(data: object) -> None | Unset | UserRef:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                actor_type_0 = UserRef.from_dict(data)

                return actor_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserRef, data)

        actor = _parse_actor(d.pop("actor", UNSET))

        def _parse_actor_token_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                actor_token_id_type_0 = UUID(data)

                return actor_token_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        actor_token_id = _parse_actor_token_id(d.pop("actor_token_id", UNSET))

        def _parse_target_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        target_type = _parse_target_type(d.pop("target_type", UNSET))

        def _parse_target_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        target_id = _parse_target_id(d.pop("target_id", UNSET))

        def _parse_ip(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ip = _parse_ip(d.pop("ip", UNSET))

        def _parse_user_agent(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_agent = _parse_user_agent(d.pop("user_agent", UNSET))

        def _parse_request_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        request_id = _parse_request_id(d.pop("request_id", UNSET))

        _details = d.pop("details", UNSET)
        details: AuditEventDetails | Unset
        if isinstance(_details, Unset):
            details = UNSET
        else:
            details = AuditEventDetails.from_dict(_details)

        audit_event = cls(
            id=id,
            created_at=created_at,
            action=action,
            outcome=outcome,
            workspace_id=workspace_id,
            actor=actor,
            actor_token_id=actor_token_id,
            target_type=target_type,
            target_id=target_id,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
            details=details,
        )

        audit_event.additional_properties = d
        return audit_event

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
