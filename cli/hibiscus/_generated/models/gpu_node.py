from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.gpu_node_status import GpuNodeStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.gpu_node_current_run_type_0 import GpuNodeCurrentRunType0
    from ..models.gpu_sample import GpuSample


T = TypeVar("T", bound="GpuNode")


@_attrs_define
class GpuNode:
    """
    Attributes:
        id (str):
        name (str):
        total_vram_mb (int):
        compute_capability (str):
        supports_bf16 (bool):
        status (GpuNodeStatus):
        supports_fast_fp16 (bool | Unset):
        last_heartbeat_at (datetime.datetime | None | Unset):
        current_run (GpuNodeCurrentRunType0 | None | Unset): Null when idle; `id`/`name` null when the run is in another
            workspace
        telemetry (GpuSample | None | Unset):
    """

    id: str
    name: str
    total_vram_mb: int
    compute_capability: str
    supports_bf16: bool
    status: GpuNodeStatus
    supports_fast_fp16: bool | Unset = UNSET
    last_heartbeat_at: datetime.datetime | None | Unset = UNSET
    current_run: GpuNodeCurrentRunType0 | None | Unset = UNSET
    telemetry: GpuSample | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.gpu_node_current_run_type_0 import GpuNodeCurrentRunType0
        from ..models.gpu_sample import GpuSample

        id = self.id

        name = self.name

        total_vram_mb = self.total_vram_mb

        compute_capability = self.compute_capability

        supports_bf16 = self.supports_bf16

        status = self.status.value

        supports_fast_fp16 = self.supports_fast_fp16

        last_heartbeat_at: None | str | Unset
        if isinstance(self.last_heartbeat_at, Unset):
            last_heartbeat_at = UNSET
        elif isinstance(self.last_heartbeat_at, datetime.datetime):
            last_heartbeat_at = self.last_heartbeat_at.isoformat()
        else:
            last_heartbeat_at = self.last_heartbeat_at

        current_run: dict[str, Any] | None | Unset
        if isinstance(self.current_run, Unset):
            current_run = UNSET
        elif isinstance(self.current_run, GpuNodeCurrentRunType0):
            current_run = self.current_run.to_dict()
        else:
            current_run = self.current_run

        telemetry: dict[str, Any] | None | Unset
        if isinstance(self.telemetry, Unset):
            telemetry = UNSET
        elif isinstance(self.telemetry, GpuSample):
            telemetry = self.telemetry.to_dict()
        else:
            telemetry = self.telemetry

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "name": name,
                "total_vram_mb": total_vram_mb,
                "compute_capability": compute_capability,
                "supports_bf16": supports_bf16,
                "status": status,
            }
        )
        if supports_fast_fp16 is not UNSET:
            field_dict["supports_fast_fp16"] = supports_fast_fp16
        if last_heartbeat_at is not UNSET:
            field_dict["last_heartbeat_at"] = last_heartbeat_at
        if current_run is not UNSET:
            field_dict["current_run"] = current_run
        if telemetry is not UNSET:
            field_dict["telemetry"] = telemetry

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.gpu_node_current_run_type_0 import GpuNodeCurrentRunType0
        from ..models.gpu_sample import GpuSample

        d = dict(src_dict)
        id = d.pop("id")

        name = d.pop("name")

        total_vram_mb = d.pop("total_vram_mb")

        compute_capability = d.pop("compute_capability")

        supports_bf16 = d.pop("supports_bf16")

        status = GpuNodeStatus(d.pop("status"))

        supports_fast_fp16 = d.pop("supports_fast_fp16", UNSET)

        def _parse_last_heartbeat_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_heartbeat_at_type_0 = isoparse(data)

                return last_heartbeat_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_heartbeat_at = _parse_last_heartbeat_at(d.pop("last_heartbeat_at", UNSET))

        def _parse_current_run(data: object) -> GpuNodeCurrentRunType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                current_run_type_0 = GpuNodeCurrentRunType0.from_dict(data)

                return current_run_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GpuNodeCurrentRunType0 | None | Unset, data)

        current_run = _parse_current_run(d.pop("current_run", UNSET))

        def _parse_telemetry(data: object) -> GpuSample | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                telemetry_type_0 = GpuSample.from_dict(data)

                return telemetry_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GpuSample | None | Unset, data)

        telemetry = _parse_telemetry(d.pop("telemetry", UNSET))

        gpu_node = cls(
            id=id,
            name=name,
            total_vram_mb=total_vram_mb,
            compute_capability=compute_capability,
            supports_bf16=supports_bf16,
            status=status,
            supports_fast_fp16=supports_fast_fp16,
            last_heartbeat_at=last_heartbeat_at,
            current_run=current_run,
            telemetry=telemetry,
        )

        gpu_node.additional_properties = d
        return gpu_node

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
