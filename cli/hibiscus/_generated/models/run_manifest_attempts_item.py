import datetime
from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="RunManifestAttemptsItem")


@_attrs_define
class RunManifestAttemptsItem:
    """
    Attributes:
        attempt (int):
        started_at (datetime.datetime):
        gpu_id (str):
        finished_at (Union[None, Unset, datetime.datetime]):
        resumed_from_step (Union[None, Unset, int]):
        exit_code (Union[None, Unset, int]):
        error_code (Union[None, Unset, str]):
    """

    attempt: int
    started_at: datetime.datetime
    gpu_id: str
    finished_at: Union[None, Unset, datetime.datetime] = UNSET
    resumed_from_step: Union[None, Unset, int] = UNSET
    exit_code: Union[None, Unset, int] = UNSET
    error_code: Union[None, Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        attempt = self.attempt

        started_at = self.started_at.isoformat()

        gpu_id = self.gpu_id

        finished_at: Union[None, Unset, str]
        if isinstance(self.finished_at, Unset):
            finished_at = UNSET
        elif isinstance(self.finished_at, datetime.datetime):
            finished_at = self.finished_at.isoformat()
        else:
            finished_at = self.finished_at

        resumed_from_step: Union[None, Unset, int]
        if isinstance(self.resumed_from_step, Unset):
            resumed_from_step = UNSET
        else:
            resumed_from_step = self.resumed_from_step

        exit_code: Union[None, Unset, int]
        if isinstance(self.exit_code, Unset):
            exit_code = UNSET
        else:
            exit_code = self.exit_code

        error_code: Union[None, Unset, str]
        if isinstance(self.error_code, Unset):
            error_code = UNSET
        else:
            error_code = self.error_code

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "attempt": attempt,
                "started_at": started_at,
                "gpu_id": gpu_id,
            }
        )
        if finished_at is not UNSET:
            field_dict["finished_at"] = finished_at
        if resumed_from_step is not UNSET:
            field_dict["resumed_from_step"] = resumed_from_step
        if exit_code is not UNSET:
            field_dict["exit_code"] = exit_code
        if error_code is not UNSET:
            field_dict["error_code"] = error_code

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        attempt = d.pop("attempt")

        started_at = isoparse(d.pop("started_at"))

        gpu_id = d.pop("gpu_id")

        def _parse_finished_at(data: object) -> Union[None, Unset, datetime.datetime]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                finished_at_type_0 = isoparse(data)

                return finished_at_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, datetime.datetime], data)

        finished_at = _parse_finished_at(d.pop("finished_at", UNSET))

        def _parse_resumed_from_step(data: object) -> Union[None, Unset, int]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, int], data)

        resumed_from_step = _parse_resumed_from_step(d.pop("resumed_from_step", UNSET))

        def _parse_exit_code(data: object) -> Union[None, Unset, int]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, int], data)

        exit_code = _parse_exit_code(d.pop("exit_code", UNSET))

        def _parse_error_code(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        error_code = _parse_error_code(d.pop("error_code", UNSET))

        run_manifest_attempts_item = cls(
            attempt=attempt,
            started_at=started_at,
            gpu_id=gpu_id,
            finished_at=finished_at,
            resumed_from_step=resumed_from_step,
            exit_code=exit_code,
            error_code=error_code,
        )

        run_manifest_attempts_item.additional_properties = d
        return run_manifest_attempts_item

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
