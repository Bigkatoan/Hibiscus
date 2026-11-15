from enum import Enum


class StreamRunEventsIncludeItem(str, Enum):
    LOG = "log"
    PROGRESS = "progress"
    TELEMETRY = "telemetry"

    def __str__(self) -> str:
        return str(self.value)
