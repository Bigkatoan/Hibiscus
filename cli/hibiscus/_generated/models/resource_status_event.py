import datetime
from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
    cast,
)
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.resource_status_event_resource import ResourceStatusEventResource
from ..types import UNSET, Unset

T = TypeVar("T", bound="ResourceStatusEvent")


@_attrs_define
class ResourceStatusEvent:
    """
    Attributes:
        resource (ResourceStatusEventResource):
        id (UUID):
        status (str):
        ts (datetime.datetime):
        error_code (Union[None, Unset, str]):
    """

    resource: ResourceStatusEventResource
    id: UUID
    status: str
    ts: datetime.datetime
    error_code: Union[None, Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        resource = self.resource.value

        id = str(self.id)

        status = self.status

        ts = self.ts.isoformat()

        error_code: Union[None, Unset, str]
        if isinstance(self.error_code, Unset):
            error_code = UNSET
        else:
            error_code = self.error_code

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "resource": resource,
                "id": id,
                "status": status,
                "ts": ts,
            }
        )
        if error_code is not UNSET:
            field_dict["error_code"] = error_code

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        resource = ResourceStatusEventResource(d.pop("resource"))

        id = UUID(d.pop("id"))

        status = d.pop("status")

        ts = isoparse(d.pop("ts"))

        def _parse_error_code(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        error_code = _parse_error_code(d.pop("error_code", UNSET))

        resource_status_event = cls(
            resource=resource,
            id=id,
            status=status,
            ts=ts,
            error_code=error_code,
        )

        resource_status_event.additional_properties = d
        return resource_status_event

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
