from enum import Enum


class OnnxSupport(str, Enum):
    FULL = "full"
    NONE = "none"
    SPLIT = "split"

    def __str__(self) -> str:
        return str(self.value)
