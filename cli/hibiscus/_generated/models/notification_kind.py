from enum import Enum


class NotificationKind(str, Enum):
    DATASET_INVALID = "dataset.invalid"
    DATASET_READY = "dataset.ready"
    INVITE_ACCEPTED = "invite.accepted"
    MODEL_FAILED = "model.failed"
    MODEL_READY = "model.ready"
    QUOTA_WARNING = "quota.warning"
    RUN_CANCELLED = "run.cancelled"
    RUN_FAILED = "run.failed"
    RUN_STALLED = "run.stalled"
    RUN_SUCCEEDED = "run.succeeded"

    def __str__(self) -> str:
        return str(self.value)
