from enum import Enum


class SearchRunLogsLevel(str, Enum):
    DEBUG = "debug"
    ERROR = "error"
    INFO = "info"
    WARNING = "warning"

    def __str__(self) -> str:
        return str(self.value)
