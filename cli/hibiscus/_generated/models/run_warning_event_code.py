from enum import Enum


class RunWarningEventCode(str, Enum):
    HELDOUT_TOO_SMALL = "heldout_too_small"
    LOG_SILENT = "log_silent"
    MIXED_PRECISION_FORCED_NO = "mixed_precision_forced_no"
    NAN_DETECTED = "nan_detected"
    PARSER_MISMATCH = "parser_mismatch"
    RETRYING_AFTER_INFRA_ERROR = "retrying_after_infra_error"
    VRAM_NEAR_LIMIT = "vram_near_limit"

    def __str__(self) -> str:
        return str(self.value)
