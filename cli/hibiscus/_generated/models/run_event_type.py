from enum import Enum


class RunEventType(str, Enum):
    CHECKPOINT = "checkpoint"
    ERROR = "error"
    EVAL = "eval"
    METRICS = "metrics"
    MODEL = "model"
    STATUS = "status"
    WARNING = "warning"

    def __str__(self) -> str:
        return str(self.value)
