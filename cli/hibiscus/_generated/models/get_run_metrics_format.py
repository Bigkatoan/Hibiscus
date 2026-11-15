from enum import Enum


class GetRunMetricsFormat(str, Enum):
    CSV = "csv"
    JSON = "json"

    def __str__(self) -> str:
        return str(self.value)
