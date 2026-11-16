from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.run_stream_event_event import RunStreamEventEvent
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.checkpoint_event import CheckpointEvent
    from ..models.end_event import EndEvent
    from ..models.eval_event import EvalEvent
    from ..models.heartbeat import Heartbeat
    from ..models.log_event import LogEvent
    from ..models.metrics_event import MetricsEvent
    from ..models.model_event import ModelEvent
    from ..models.progress_event import ProgressEvent
    from ..models.run_error_event import RunErrorEvent
    from ..models.run_status_event import RunStatusEvent
    from ..models.run_warning_event import RunWarningEvent
    from ..models.telemetry_event import TelemetryEvent


T = TypeVar("T", bound="RunStreamEvent")


@_attrs_define
class RunStreamEvent:
    """Documentation schema for one SSE message on /runs/{run_id}/events. `event` is the SSE
    `event:` field, `data` the JSON in `data:`, `id` the SSE `id:` (persisted events only).

        Attributes:
            event (RunStreamEventEvent):
            data (CheckpointEvent | EndEvent | EvalEvent | Heartbeat | LogEvent | MetricsEvent | ModelEvent | ProgressEvent
                | RunErrorEvent | RunStatusEvent | RunWarningEvent | TelemetryEvent):
            id (int | Unset): run_events.seq
    """

    event: RunStreamEventEvent
    data: (
        CheckpointEvent
        | EndEvent
        | EvalEvent
        | Heartbeat
        | LogEvent
        | MetricsEvent
        | ModelEvent
        | ProgressEvent
        | RunErrorEvent
        | RunStatusEvent
        | RunWarningEvent
        | TelemetryEvent
    )
    id: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.checkpoint_event import CheckpointEvent
        from ..models.eval_event import EvalEvent
        from ..models.heartbeat import Heartbeat
        from ..models.log_event import LogEvent
        from ..models.metrics_event import MetricsEvent
        from ..models.model_event import ModelEvent
        from ..models.progress_event import ProgressEvent
        from ..models.run_error_event import RunErrorEvent
        from ..models.run_status_event import RunStatusEvent
        from ..models.run_warning_event import RunWarningEvent
        from ..models.telemetry_event import TelemetryEvent

        event = self.event.value

        data: dict[str, Any]
        if isinstance(self.data, RunStatusEvent):
            data = self.data.to_dict()
        elif isinstance(self.data, MetricsEvent):
            data = self.data.to_dict()
        elif isinstance(self.data, CheckpointEvent):
            data = self.data.to_dict()
        elif isinstance(self.data, RunWarningEvent):
            data = self.data.to_dict()
        elif isinstance(self.data, RunErrorEvent):
            data = self.data.to_dict()
        elif isinstance(self.data, ModelEvent):
            data = self.data.to_dict()
        elif isinstance(self.data, EvalEvent):
            data = self.data.to_dict()
        elif isinstance(self.data, ProgressEvent):
            data = self.data.to_dict()
        elif isinstance(self.data, LogEvent):
            data = self.data.to_dict()
        elif isinstance(self.data, TelemetryEvent):
            data = self.data.to_dict()
        elif isinstance(self.data, Heartbeat):
            data = self.data.to_dict()
        else:
            data = self.data.to_dict()

        id = self.id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "event": event,
                "data": data,
            }
        )
        if id is not UNSET:
            field_dict["id"] = id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.checkpoint_event import CheckpointEvent
        from ..models.end_event import EndEvent
        from ..models.eval_event import EvalEvent
        from ..models.heartbeat import Heartbeat
        from ..models.log_event import LogEvent
        from ..models.metrics_event import MetricsEvent
        from ..models.model_event import ModelEvent
        from ..models.progress_event import ProgressEvent
        from ..models.run_error_event import RunErrorEvent
        from ..models.run_status_event import RunStatusEvent
        from ..models.run_warning_event import RunWarningEvent
        from ..models.telemetry_event import TelemetryEvent

        d = dict(src_dict)
        event = RunStreamEventEvent(d.pop("event"))

        def _parse_data(
            data: object,
        ) -> (
            CheckpointEvent
            | EndEvent
            | EvalEvent
            | Heartbeat
            | LogEvent
            | MetricsEvent
            | ModelEvent
            | ProgressEvent
            | RunErrorEvent
            | RunStatusEvent
            | RunWarningEvent
            | TelemetryEvent
        ):
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_0 = RunStatusEvent.from_dict(data)

                return data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_1 = MetricsEvent.from_dict(data)

                return data_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_2 = CheckpointEvent.from_dict(data)

                return data_type_2
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_3 = RunWarningEvent.from_dict(data)

                return data_type_3
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_4 = RunErrorEvent.from_dict(data)

                return data_type_4
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_5 = ModelEvent.from_dict(data)

                return data_type_5
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_6 = EvalEvent.from_dict(data)

                return data_type_6
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_7 = ProgressEvent.from_dict(data)

                return data_type_7
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_8 = LogEvent.from_dict(data)

                return data_type_8
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_9 = TelemetryEvent.from_dict(data)

                return data_type_9
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_10 = Heartbeat.from_dict(data)

                return data_type_10
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            data_type_11 = EndEvent.from_dict(data)

            return data_type_11

        data = _parse_data(d.pop("data"))

        id = d.pop("id", UNSET)

        run_stream_event = cls(
            event=event,
            data=data,
            id=id,
        )

        run_stream_event.additional_properties = d
        return run_stream_event

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
