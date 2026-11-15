from enum import Enum


class RunErrorCode(str, Enum):
    CHECKPOINT_CORRUPT = "checkpoint_corrupt"
    CONFIG_INVALID = "config_invalid"
    DATASET_FEATURE_MISMATCH = "dataset_feature_mismatch"
    DATASET_UNAVAILABLE = "dataset_unavailable"
    EXPORT_FAILED = "export_failed"
    GPU_ERROR = "gpu_error"
    INTERNAL_ERROR = "internal_error"
    NAN_LOSS = "nan_loss"
    OOM = "oom"
    PROCESS_CRASHED = "process_crashed"
    QUOTA_EXCEEDED = "quota_exceeded"
    STALLED = "stalled"
    STORAGE_ERROR = "storage_error"
    WORKER_LOST = "worker_lost"

    def __str__(self) -> str:
        return str(self.value)
