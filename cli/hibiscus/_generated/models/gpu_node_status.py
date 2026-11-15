from enum import Enum


class GpuNodeStatus(str, Enum):
    DISABLED = "disabled"
    DRAINING = "draining"
    OFFLINE = "offline"
    ONLINE = "online"

    def __str__(self) -> str:
        return str(self.value)
