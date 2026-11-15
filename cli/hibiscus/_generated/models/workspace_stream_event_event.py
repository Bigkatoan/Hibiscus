from enum import Enum


class WorkspaceStreamEventEvent(str, Enum):
    DATASET_VERSION_STATUS = "dataset_version.status"
    ESTIMATE_READY = "estimate.ready"
    HEARTBEAT = "heartbeat"
    JOB_STATUS = "job.status"
    MODEL_STATUS = "model.status"
    NOTIFICATION = "notification"
    RUN_STATUS = "run.status"

    def __str__(self) -> str:
        return str(self.value)
