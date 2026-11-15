from enum import Enum


class PolicySummaryGpuSupportAdditionalProperty(str, Enum):
    LIMITED = "limited"
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"

    def __str__(self) -> str:
        return str(self.value)
