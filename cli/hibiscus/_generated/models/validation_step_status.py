from enum import Enum


class ValidationStepStatus(str, Enum):
    FAILED = "failed"
    PASSED = "passed"
    PENDING = "pending"
    RUNNING = "running"
    SKIPPED = "skipped"
    WARNING = "warning"

    def __str__(self) -> str:
        return str(self.value)
