from enum import Enum


class PolicyType(str, Enum):
    ACT = "act"
    DIFFUSION = "diffusion"
    PI0 = "pi0"
    PI05 = "pi05"
    SMOLVLA = "smolvla"
    TDMPC = "tdmpc"
    VQBET = "vqbet"

    def __str__(self) -> str:
        return str(self.value)
