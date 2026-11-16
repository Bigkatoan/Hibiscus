from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.run_event_record_level import RunEventRecordLevel
from ..models.run_event_type import RunEventType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.checkpoint_event import CheckpointEvent
    from ..models.eval_event import EvalEvent
    from ..models.metrics_event import MetricsEvent
    from ..models.model_event import ModelEvent
    from ..models.run_error_event import RunErrorEvent
    from ..models.run_status_event import RunStatusEvent
    from ..models.run_warning_event import RunWarningEvent


T = TypeVar("T", bound="RunEventRecord")


@_attrs_define
class RunEventRecord:
    """
    Attributes:
        seq (int):
        type_ (RunEventType): Persisted (have SSE id) event types
        ts (datetime.datetime):
        attempt (int):
        data (CheckpointEvent | EvalEvent | MetricsEvent | ModelEvent | RunErrorEvent | RunStatusEvent |
            RunWarningEvent):
        level (RunEventRecordLevel | Unset):
    """

    seq: int
    type_: RunEventType
    ts: datetime.datetime
    attempt: int
    data: (
        CheckpointEvent
        | EvalEvent
        | MetricsEvent
        | ModelEvent
        | RunErrorEvent
        | RunStatusEvent
        | RunWarningEvent
    )
    level: RunEventRecordLevel | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.checkpoint_event import CheckpointEvent
        from ..models.metrics_event import MetricsEvent
        from ..models.model_event import ModelEvent
        from ..models.run_error_event import RunErrorEvent
        from ..models.run_status_event import RunStatusEvent
        from ..models.run_warning_event import RunWarningEvent

        seq = self.seq

        type_ = self.type_.value

        ts = self.ts.isoformat()

        attempt = self.attempt

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
        else:
            data = self.data.to_dict()

        level: str | Unset = UNSET
        if not isinstance(self.level, Unset):
            level = self.level.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "seq": seq,
                "type": type_,
                "ts": ts,
                "attempt": attempt,
                "data": data,
            }
        )
        if level is not UNSET:
            field_dict["level"] = level

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.checkpoint_event import CheckpointEvent
        from ..models.eval_event import EvalEvent
        from ..models.metrics_event import MetricsEvent
        from ..models.model_event import ModelEvent
        from ..models.run_error_event import RunErrorEvent
        from ..models.run_status_event import RunStatusEvent
        from ..models.run_warning_event import RunWarningEvent

        d = dict(src_dict)
        seq = d.pop("seq")

        type_ = RunEventType(d.pop("type"))

        ts = isoparse(d.pop("ts"))

        attempt = d.pop("attempt")

        def _parse_data(
            data: object,
        ) -> (
            CheckpointEvent
            | EvalEvent
            | MetricsEvent
            | ModelEvent
            | RunErrorEvent
            | RunStatusEvent
            | RunWarningEvent
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
            if not isinstance(data, dict):
                raise TypeError()
            data_type_6 = EvalEvent.from_dict(data)

            return data_type_6

        data = _parse_data(d.pop("data"))

        _level = d.pop("level", UNSET)
        level: RunEventRecordLevel | Unset
        if isinstance(_level, Unset):
            level = UNSET
        else:
            level = RunEventRecordLevel(_level)

        run_event_record = cls(
            seq=seq,
            type_=type_,
            ts=ts,
            attempt=attempt,
            data=data,
            level=level,
        )

        run_event_record.additional_properties = d
        return run_event_record

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
