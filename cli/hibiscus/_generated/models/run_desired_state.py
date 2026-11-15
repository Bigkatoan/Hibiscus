from enum import Enum


class RunDesiredState(str, Enum):
    CANCEL = "cancel"
    PAUSE = "pause"
    PAUSE_NOW = "pause_now"
    RUN = "run"

    def __str__(self) -> str:
        return str(self.value)
