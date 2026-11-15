from enum import Enum


class AuditEventOutcome(str, Enum):
    DENIED = "denied"
    FAILURE = "failure"
    SUCCESS = "success"

    def __str__(self) -> str:
        return str(self.value)
