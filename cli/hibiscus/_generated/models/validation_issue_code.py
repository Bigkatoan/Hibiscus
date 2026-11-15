from enum import Enum


class ValidationIssueCode(str, Enum):
    ARCHIVE_BOMB = "archive_bomb"
    ARCHIVE_CORRUPT = "archive_corrupt"
    ARCHIVE_SYMLINK = "archive_symlink"
    ARCHIVE_TOO_LARGE = "archive_too_large"
    ARCHIVE_UNSAFE_PATH = "archive_unsafe_path"
    CAMERA_SHAPE_MISMATCH = "camera_shape_mismatch"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    CONVERSION_FAILED = "conversion_failed"
    DATASET_ROOT_NOT_FOUND = "dataset_root_not_found"
    EPISODE_TOO_SHORT = "episode_too_short"
    FEATURE_MISSING = "feature_missing"
    FEATURE_SHAPE_INVALID = "feature_shape_invalid"
    FRAME_COUNT_MISMATCH = "frame_count_mismatch"
    INFO_JSON_INVALID = "info_json_invalid"
    JOINT_NAMES_MISMATCH = "joint_names_mismatch"
    MISSING_FILE = "missing_file"
    MULTIPLE_DATASET_ROOTS = "multiple_dataset_roots"
    NAN_VALUES = "nan_values"
    NO_CAMERA = "no_camera"
    STATS_MISMATCH = "stats_mismatch"
    STATS_MISSING = "stats_missing"
    TASK_MISSING = "task_missing"
    TIMESTAMP_FPS_MISMATCH = "timestamp_fps_mismatch"
    TIMESTAMP_IRREGULAR = "timestamp_irregular"
    UNSUPPORTED_CODEBASE_VERSION = "unsupported_codebase_version"
    VIDEO_DECODE_FAILED = "video_decode_failed"
    VIDEO_MISSING = "video_missing"

    def __str__(self) -> str:
        return str(self.value)
