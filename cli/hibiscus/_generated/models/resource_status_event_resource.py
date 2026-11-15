from enum import Enum


class ResourceStatusEventResource(str, Enum):
    DATASET_VERSION = "dataset_version"
    ESTIMATE = "estimate"
    JOB = "job"
    MODEL = "model"

    def __str__(self) -> str:
        return str(self.value)
