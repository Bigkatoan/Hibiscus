from enum import Enum


class ValidationSummaryResult(str, Enum):
    FAILED = "failed"
    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    RUNNING = "running"

    def __str__(self) -> str:
        return str(self.value)
