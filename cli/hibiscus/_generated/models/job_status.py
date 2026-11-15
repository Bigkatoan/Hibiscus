from enum import Enum


class JobStatus(str, Enum):
    CANCELLED = "cancelled"
    FAILED = "failed"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"

    def __str__(self) -> str:
        return str(self.value)
