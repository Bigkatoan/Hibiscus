from enum import Enum


class NotificationChannelCreateEventsItem(str, Enum):
    DATASET_INVALID = "dataset.invalid"
    DATASET_READY = "dataset.ready"
    MODEL_READY = "model.ready"
    RUN_FAILED = "run.failed"
    RUN_STALLED = "run.stalled"
    RUN_SUCCEEDED = "run.succeeded"

    def __str__(self) -> str:
        return str(self.value)
