from enum import Enum


class LoginResultStatus(str, Enum):
    MFA_REQUIRED = "mfa_required"
    OK = "ok"

    def __str__(self) -> str:
        return str(self.value)
