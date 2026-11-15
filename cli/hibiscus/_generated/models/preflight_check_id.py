from enum import Enum


class PreflightCheckId(str, Enum):
    CAMERA_KEYS = "camera_keys"
    CONFIG_SCHEMA = "config_schema"
    CROSS_FIELD = "cross_field"
    DATASET_READY = "dataset_ready"
    FEATURE_DIMS = "feature_dims"
    GPU_AVAILABLE = "gpu_available"
    INIT_FROM = "init_from"
    MIXED_PRECISION = "mixed_precision"
    POLICY_REQUIREMENTS = "policy_requirements"
    QUOTA = "quota"
    VRAM = "vram"

    def __str__(self) -> str:
        return str(self.value)
