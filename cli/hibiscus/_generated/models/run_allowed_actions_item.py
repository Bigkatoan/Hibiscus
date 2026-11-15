from enum import Enum


class RunAllowedActionsItem(str, Enum):
    CANCEL = "cancel"
    CLONE = "clone"
    EDIT = "edit"
    EVAL = "eval"
    EXPORT = "export"
    PAUSE = "pause"
    RESUME = "resume"

    def __str__(self) -> str:
        return str(self.value)
