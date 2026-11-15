from enum import Enum


class UploadStatus(str, Enum):
    ABORTED = "aborted"
    ACTIVE = "active"
    COMPLETED = "completed"
    COMPLETING = "completing"
    EXPIRED = "expired"
    FAILED = "failed"

    def __str__(self) -> str:
        return str(self.value)
