from enum import Enum


class MixedPrecision(str, Enum):
    BF16 = "bf16"
    FP16 = "fp16"
    NO = "no"

    def __str__(self) -> str:
        return str(self.value)
