import datetime
from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    Union,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.run_error_code import RunErrorCode
from ..types import UNSET, Unset

T = TypeVar("T", bound="RunErrorEvent")


@_attrs_define
class RunErrorEvent:
    """
    Attributes:
        kind (Literal['error']):
        code (RunErrorCode): Run.error_code catalogue (docs/spec/run-lifecycle.md §6). `infra` codes are auto-retried
            once.
        message (str):
        ts (datetime.datetime):
        log_excerpt (Union[None, Unset, str]): Last <= 50 log lines
        will_retry (Union[Unset, bool]):
    """

    kind: Literal["error"]
    code: RunErrorCode
    message: str
    ts: datetime.datetime
    log_excerpt: Union[None, Unset, str] = UNSET
    will_retry: Union[Unset, bool] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        kind = self.kind

        code = self.code.value

        message = self.message

        ts = self.ts.isoformat()

        log_excerpt: Union[None, Unset, str]
        if isinstance(self.log_excerpt, Unset):
            log_excerpt = UNSET
        else:
            log_excerpt = self.log_excerpt

        will_retry = self.will_retry

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "kind": kind,
                "code": code,
                "message": message,
                "ts": ts,
            }
        )
        if log_excerpt is not UNSET:
            field_dict["log_excerpt"] = log_excerpt
        if will_retry is not UNSET:
            field_dict["will_retry"] = will_retry

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        kind = cast(Literal["error"], d.pop("kind"))
        if kind != "error":
            raise ValueError(f"kind must match const 'error', got '{kind}'")

        code = RunErrorCode(d.pop("code"))

        message = d.pop("message")

        ts = isoparse(d.pop("ts"))

        def _parse_log_excerpt(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        log_excerpt = _parse_log_excerpt(d.pop("log_excerpt", UNSET))

        will_retry = d.pop("will_retry", UNSET)

        run_error_event = cls(
            kind=kind,
            code=code,
            message=message,
            ts=ts,
            log_excerpt=log_excerpt,
            will_retry=will_retry,
        )

        run_error_event.additional_properties = d
        return run_error_event

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
