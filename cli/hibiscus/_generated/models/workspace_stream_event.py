from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    Union,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.workspace_stream_event_event import WorkspaceStreamEventEvent

if TYPE_CHECKING:
    from ..models.heartbeat import Heartbeat
    from ..models.notification import Notification
    from ..models.resource_status_event import ResourceStatusEvent
    from ..models.run_status_event import RunStatusEvent


T = TypeVar("T", bound="WorkspaceStreamEvent")


@_attrs_define
class WorkspaceStreamEvent:
    """SSE: `event: <event>` / `data: <payload JSON>`; heartbeat payload `{"ts": ...}`

    Attributes:
        event (WorkspaceStreamEventEvent):
        data (Union['Heartbeat', 'Notification', 'ResourceStatusEvent', 'RunStatusEvent']):
    """

    event: WorkspaceStreamEventEvent
    data: Union["Heartbeat", "Notification", "ResourceStatusEvent", "RunStatusEvent"]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.heartbeat import Heartbeat
        from ..models.resource_status_event import ResourceStatusEvent
        from ..models.run_status_event import RunStatusEvent

        event = self.event.value

        data: dict[str, Any]
        if isinstance(self.data, Heartbeat):
            data = self.data.to_dict()
        elif isinstance(self.data, RunStatusEvent):
            data = self.data.to_dict()
        elif isinstance(self.data, ResourceStatusEvent):
            data = self.data.to_dict()
        else:
            data = self.data.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "event": event,
                "data": data,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.heartbeat import Heartbeat
        from ..models.notification import Notification
        from ..models.resource_status_event import ResourceStatusEvent
        from ..models.run_status_event import RunStatusEvent

        d = dict(src_dict)
        event = WorkspaceStreamEventEvent(d.pop("event"))

        def _parse_data(
            data: object,
        ) -> Union[
            "Heartbeat", "Notification", "ResourceStatusEvent", "RunStatusEvent"
        ]:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_0 = Heartbeat.from_dict(data)

                return data_type_0
            except:  # noqa: E722
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_1 = RunStatusEvent.from_dict(data)

                return data_type_1
            except:  # noqa: E722
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_2 = ResourceStatusEvent.from_dict(data)

                return data_type_2
            except:  # noqa: E722
                pass
            if not isinstance(data, dict):
                raise TypeError()
            data_type_3 = Notification.from_dict(data)

            return data_type_3

        data = _parse_data(d.pop("data"))

        workspace_stream_event = cls(
            event=event,
            data=data,
        )

        workspace_stream_event.additional_properties = d
        return workspace_stream_event

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
