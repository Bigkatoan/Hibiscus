from enum import Enum


class PatScope(str, Enum):
    DATASETSREAD = "datasets:read"
    DATASETSWRITE = "datasets:write"
    MODELSREAD = "models:read"
    RUNSREAD = "runs:read"
    RUNSWRITE = "runs:write"

    def __str__(self) -> str:
        return str(self.value)
