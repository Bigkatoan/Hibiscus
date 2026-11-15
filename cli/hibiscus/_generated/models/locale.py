from enum import Enum


class Locale(str, Enum):
    EN = "en"
    VI = "vi"

    def __str__(self) -> str:
        return str(self.value)
