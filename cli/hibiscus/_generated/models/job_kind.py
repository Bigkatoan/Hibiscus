from enum import Enum


class JobKind(str, Enum):
    ESTIMATE_RESOURCES = "estimate_resources"
    EVAL_CHECKPOINT = "eval_checkpoint"
    EXPORT_MODEL = "export_model"
    IMPORT_HF_DATASET = "import_hf_dataset"
    MERGE_DATASETS = "merge_datasets"
    PUSH_MODEL_HUB = "push_model_hub"
    VALIDATE_DATASET = "validate_dataset"

    def __str__(self) -> str:
        return str(self.value)
