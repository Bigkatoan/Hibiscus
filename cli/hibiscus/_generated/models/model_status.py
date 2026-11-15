from enum import Enum


class ModelStatus(str, Enum):
    BUILDING = "building"
    FAILED = "failed"
    PENDING = "pending"
    READY = "ready"

    def __str__(self) -> str:
        return str(self.value)
