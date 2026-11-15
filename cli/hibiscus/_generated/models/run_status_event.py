import datetime
from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    Union,
    cast,
)
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.run_error_code import RunErrorCode
from ..models.run_status import RunStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="RunStatusEvent")


@_attrs_define
class RunStatusEvent:
    """
    Attributes:
        kind (Literal['status']):
        run_id (UUID):
        from_ (Union[None, RunStatus]):
        to (RunStatus): State machine in docs/spec/run-lifecycle.md
        ts (datetime.datetime):
        reason (Union[None, Unset, str]): e.g. user_cancel, user_pause, lease_expired, infra_retry, completed
        error_code (Union[None, RunErrorCode, Unset]):
        attempt (Union[Unset, int]):
        gpu_id (Union[None, Unset, str]):
    """

    kind: Literal["status"]
    run_id: UUID
    from_: Union[None, RunStatus]
    to: RunStatus
    ts: datetime.datetime
    reason: Union[None, Unset, str] = UNSET
    error_code: Union[None, RunErrorCode, Unset] = UNSET
    attempt: Union[Unset, int] = UNSET
    gpu_id: Union[None, Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        kind = self.kind

        run_id = str(self.run_id)

        from_: Union[None, str]
        if isinstance(self.from_, RunStatus):
            from_ = self.from_.value
        else:
            from_ = self.from_

        to = self.to.value

        ts = self.ts.isoformat()

        reason: Union[None, Unset, str]
        if isinstance(self.reason, Unset):
            reason = UNSET
        else:
            reason = self.reason

        error_code: Union[None, Unset, str]
        if isinstance(self.error_code, Unset):
            error_code = UNSET
        elif isinstance(self.error_code, RunErrorCode):
            error_code = self.error_code.value
        else:
            error_code = self.error_code

        attempt = self.attempt

        gpu_id: Union[None, Unset, str]
        if isinstance(self.gpu_id, Unset):
            gpu_id = UNSET
        else:
            gpu_id = self.gpu_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "kind": kind,
                "run_id": run_id,
                "from": from_,
                "to": to,
                "ts": ts,
            }
        )
        if reason is not UNSET:
            field_dict["reason"] = reason
        if error_code is not UNSET:
            field_dict["error_code"] = error_code
        if attempt is not UNSET:
            field_dict["attempt"] = attempt
        if gpu_id is not UNSET:
            field_dict["gpu_id"] = gpu_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        kind = cast(Literal["status"], d.pop("kind"))
        if kind != "status":
            raise ValueError(f"kind must match const 'status', got '{kind}'")

        run_id = UUID(d.pop("run_id"))

        def _parse_from_(data: object) -> Union[None, RunStatus]:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                from_type_0 = RunStatus(data)

                return from_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, RunStatus], data)

        from_ = _parse_from_(d.pop("from"))

        to = RunStatus(d.pop("to"))

        ts = isoparse(d.pop("ts"))

        def _parse_reason(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        reason = _parse_reason(d.pop("reason", UNSET))

        def _parse_error_code(data: object) -> Union[None, RunErrorCode, Unset]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                error_code_type_0 = RunErrorCode(data)

                return error_code_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, RunErrorCode, Unset], data)

        error_code = _parse_error_code(d.pop("error_code", UNSET))

        attempt = d.pop("attempt", UNSET)

        def _parse_gpu_id(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        gpu_id = _parse_gpu_id(d.pop("gpu_id", UNSET))

        run_status_event = cls(
            kind=kind,
            run_id=run_id,
            from_=from_,
            to=to,
            ts=ts,
            reason=reason,
            error_code=error_code,
            attempt=attempt,
            gpu_id=gpu_id,
        )

        run_status_event.additional_properties = d
        return run_status_event

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
