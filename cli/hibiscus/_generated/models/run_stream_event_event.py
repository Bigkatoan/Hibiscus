from enum import Enum


class RunStreamEventEvent(str, Enum):
    CHECKPOINT = "checkpoint"
    END = "end"
    ERROR = "error"
    EVAL = "eval"
    HEARTBEAT = "heartbeat"
    LOG = "log"
    METRICS = "metrics"
    MODEL = "model"
    PROGRESS = "progress"
    STATUS = "status"
    TELEMETRY = "telemetry"
    WARNING = "warning"

    def __str__(self) -> str:
        return str(self.value)
