from enum import Enum


class ValidationStepId(str, Enum):
    CHECKSUM = "checksum"
    DECODE = "decode"
    SCHEMA = "schema"
    STATS = "stats"
    STRUCTURE = "structure"
    TIMESTAMPS = "timestamps"
    UNPACK = "unpack"

    def __str__(self) -> str:
        return str(self.value)
