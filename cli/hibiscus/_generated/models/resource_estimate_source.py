from enum import Enum


class ResourceEstimateSource(str, Enum):
    CACHED = "cached"
    HEURISTIC = "heuristic"
    MEASURED = "measured"
    PENDING = "pending"

    def __str__(self) -> str:
        return str(self.value)
