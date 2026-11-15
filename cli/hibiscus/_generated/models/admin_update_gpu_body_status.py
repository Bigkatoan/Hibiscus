from enum import Enum


class AdminUpdateGpuBodyStatus(str, Enum):
    DISABLED = "disabled"
    DRAINING = "draining"
    ONLINE = "online"

    def __str__(self) -> str:
        return str(self.value)
