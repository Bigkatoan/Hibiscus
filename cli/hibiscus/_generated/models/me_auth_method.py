from enum import Enum


class MeAuthMethod(str, Enum):
    PAT = "pat"
    SESSION = "session"

    def __str__(self) -> str:
        return str(self.value)
