from enum import Enum


class NotificationChannelKind(str, Enum):
    DISCORD = "discord"
    EMAIL = "email"
    TELEGRAM = "telegram"
    WEBHOOK = "webhook"

    def __str__(self) -> str:
        return str(self.value)
