from enum import Enum


class ReadinessStatus(str, Enum):
    NOT_READY = "not_ready"
    READY = "ready"

    def __str__(self) -> str:
        return str(self.value)
