"""Request bodies for /auth/* and /users/* (api/openapi.yaml components.schemas). Unknown fields => 422."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from app.db.models import PatScope

Password = Annotated[str, StringConstraints(min_length=12, max_length=256)]
AnyPassword = Annotated[str, StringConstraints(min_length=1, max_length=256)]
TotpCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]
RecoveryCode = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]{5}-[a-z0-9]{5}$")]
OpaqueToken = Annotated[str, StringConstraints(min_length=32, max_length=128)]
Turnstile = Annotated[str, StringConstraints(max_length=2048)]
Email = Annotated[EmailStr, StringConstraints(max_length=320)]
# Login / forgot-password accept any plausible address: a strict validator would turn some
# addresses into 4xx validation errors instead of the uniform "invalid credentials" answer.
LooseEmail = Annotated[str, StringConstraints(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")]
Locale = Literal["vi", "en"]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(_Body):
    email: LooseEmail
    password: AnyPassword
    turnstile_token: Turnstile | None = None


class LoginSecondFactorRequest(_Body):
    mfa_token: OpaqueToken
    code: TotpCode | None = None
    recovery_code: RecoveryCode | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> LoginSecondFactorRequest:
        if (self.code is None) == (self.recovery_code is None):
            raise ValueError("exactly one of code / recovery_code is required")
        return self


class RegisterInviteRequest(_Body):
    invite_token: OpaqueToken
    display_name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    password: Password
    locale: Locale | None = None
    turnstile_token: Turnstile | None = None


class TokenRequest(_Body):
    token: OpaqueToken


class ForgotPasswordRequest(_Body):
    email: LooseEmail
    turnstile_token: Turnstile | None = None


class ResetPasswordRequest(_Body):
    token: OpaqueToken
    new_password: Password


class ChangePasswordRequest(_Body):
    current_password: AnyPassword
    new_password: Password


class PasswordConfirmRequest(_Body):
    password: AnyPassword


class TotpCodeRequest(_Body):
    code: TotpCode


class TotpDisableRequest(_Body):
    password: AnyPassword
    code: TotpCode


class ApiTokenCreate(_Body):
    name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    workspace_id: uuid.UUID
    scopes: Annotated[list[PatScope], Field(min_length=1)]
    expires_in_days: Annotated[int, Field(ge=1, le=365)] | None = 90

    @model_validator(mode="after")
    def _unique(self) -> ApiTokenCreate:
        if len(set(self.scopes)) != len(self.scopes):
            raise ValueError("scopes must be unique")
        return self


class UserUpdate(_Body):
    display_name: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    locale: Locale | None = None

    @model_validator(mode="after")
    def _non_empty(self) -> UserUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one property is required")
        if "display_name" in self.model_fields_set and self.display_name is None:
            raise ValueError("display_name cannot be null")
        if "locale" in self.model_fields_set and self.locale is None:
            raise ValueError("locale cannot be null")
        return self


class HfTokenSet(_Body):
    token: Annotated[str, StringConstraints(min_length=8, max_length=256)]
