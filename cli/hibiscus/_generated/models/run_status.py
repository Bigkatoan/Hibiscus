from enum import Enum


class RunStatus(str, Enum):
    CANCELLED = "cancelled"
    CANCELLING = "cancelling"
    EXPORTING = "exporting"
    FAILED = "failed"
    PAUSED = "paused"
    PAUSING = "pausing"
    PREPARING = "preparing"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"

    def __str__(self) -> str:
        return str(self.value)
