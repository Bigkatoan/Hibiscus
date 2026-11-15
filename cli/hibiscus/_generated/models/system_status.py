from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.gpu_node import GpuNode
    from ..models.system_status_email import SystemStatusEmail
    from ..models.system_status_storage import SystemStatusStorage


T = TypeVar("T", bound="SystemStatus")


@_attrs_define
class SystemStatus:
    """
    Attributes:
        hibiscus_version (str):
        lerobot_version (str):
        api_version (Literal['0.1.0']):
        queue_depth (int):
        gpus (list['GpuNode']):
        storage (SystemStatusStorage):
        email (SystemStatusEmail):
    """

    hibiscus_version: str
    lerobot_version: str
    api_version: Literal["0.1.0"]
    queue_depth: int
    gpus: list["GpuNode"]
    storage: "SystemStatusStorage"
    email: "SystemStatusEmail"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        hibiscus_version = self.hibiscus_version

        lerobot_version = self.lerobot_version

        api_version = self.api_version

        queue_depth = self.queue_depth

        gpus = []
        for gpus_item_data in self.gpus:
            gpus_item = gpus_item_data.to_dict()
            gpus.append(gpus_item)

        storage = self.storage.to_dict()

        email = self.email.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "hibiscus_version": hibiscus_version,
                "lerobot_version": lerobot_version,
                "api_version": api_version,
                "queue_depth": queue_depth,
                "gpus": gpus,
                "storage": storage,
                "email": email,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.gpu_node import GpuNode
        from ..models.system_status_email import SystemStatusEmail
        from ..models.system_status_storage import SystemStatusStorage

        d = dict(src_dict)
        hibiscus_version = d.pop("hibiscus_version")

        lerobot_version = d.pop("lerobot_version")

        api_version = cast(Literal["0.1.0"], d.pop("api_version"))
        if api_version != "0.1.0":
            raise ValueError(
                f"api_version must match const '0.1.0', got '{api_version}'"
            )

        queue_depth = d.pop("queue_depth")

        gpus = []
        _gpus = d.pop("gpus")
        for gpus_item_data in _gpus:
            gpus_item = GpuNode.from_dict(gpus_item_data)

            gpus.append(gpus_item)

        storage = SystemStatusStorage.from_dict(d.pop("storage"))

        email = SystemStatusEmail.from_dict(d.pop("email"))

        system_status = cls(
            hibiscus_version=hibiscus_version,
            lerobot_version=lerobot_version,
            api_version=api_version,
            queue_depth=queue_depth,
            gpus=gpus,
            storage=storage,
            email=email,
        )

        system_status.additional_properties = d
        return system_status

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
