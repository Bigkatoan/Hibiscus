from enum import Enum


class SystemStatusEmailProvider(str, Enum):
    CLOUDFLARE = "cloudflare"
    NONE = "none"
    RESEND = "resend"
    SES = "ses"
    SMTP = "smtp"

    def __str__(self) -> str:
        return str(self.value)
