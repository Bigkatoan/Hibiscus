from enum import Enum


class OnnxStatus(str, Enum):
    EXPORTING = "exporting"
    FAILED = "failed"
    NOT_SUPPORTED = "not_supported"
    PASSED = "passed"
    PENDING = "pending"

    def __str__(self) -> str:
        return str(self.value)
