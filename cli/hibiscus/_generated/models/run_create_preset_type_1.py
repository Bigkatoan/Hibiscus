from enum import Enum


class RunCreatePresetType1(str, Enum):
    FINETUNE = "finetune"
    QUICK = "quick"
    STANDARD = "standard"

    def __str__(self) -> str:
        return str(self.value)
