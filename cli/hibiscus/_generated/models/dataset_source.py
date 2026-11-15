from enum import Enum


class DatasetSource(str, Enum):
    HF_IMPORT = "hf_import"
    MERGE = "merge"
    UPLOAD = "upload"

    def __str__(self) -> str:
        return str(self.value)
