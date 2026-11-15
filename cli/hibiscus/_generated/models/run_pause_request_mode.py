from enum import Enum


class RunPauseRequestMode(str, Enum):
    NEXT_CHECKPOINT = "next_checkpoint"
    NOW = "now"

    def __str__(self) -> str:
        return str(self.value)
