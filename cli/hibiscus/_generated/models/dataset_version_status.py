from enum import Enum


class DatasetVersionStatus(str, Enum):
    FAILED = "failed"
    INVALID = "invalid"
    PENDING = "pending"
    READY = "ready"
    UNPACKING = "unpacking"
    VALIDATING = "validating"

    def __str__(self) -> str:
        return str(self.value)
