"""Application settings (pydantic-settings, env prefix ``HIBISCUS_``).

Every secret can also be supplied as a Docker secret file: ``HIBISCUS_<NAME>_FILE=/run/secrets/x``
(see :func:`_load_file_secrets`). Nothing secret has a production default.

In ``env=dev``/``test`` missing keys (JWT signing key, data key, cursor secret) are never random per
process — every uvicorn worker of a deployment must sign and verify with the same key (QC-e2e-02):

1. ``HIBISCUS_DEV_SECRET`` set: each key is derived deterministically from it (HKDF-SHA256, one
   ``info`` label per key), so every process/container sharing the secret agrees;
2. otherwise the keys are generated once and persisted in ``HIBISCUS_DEV_KEYS_FILE`` (default
   ``$XDG_RUNTIME_DIR/hibiscus-dev-keys.json`` or ``<tmpdir>/hibiscus-dev-keys-<uid>.json``, created
   atomically, mode 0600, and only trusted when owned by us with mode 0600); concurrent workers that race
   on start-up all end up reading the first file written.
"""

from __future__ import annotations

import base64
import contextlib
import errno
import ipaddress
import json
import os
import secrets
import stat
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EmailProvider = Literal["none", "smtp", "cloudflare"]

_FILE_SECRETS = (
    "JWT_PRIVATE_KEY",
    "DATA_KEY",
    "CURSOR_SECRET",
    "DATABASE_URL",
    "REDIS_URL",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "SMTP_PASSWORD",
    "EMAIL_WORKER_SECRET",
    "TURNSTILE_SECRET_KEY",
)


def _load_file_secrets() -> None:
    """``HIBISCUS_X_FILE`` -> ``HIBISCUS_X`` (Docker secrets convention). Explicit env wins."""
    for name in _FILE_SECRETS:
        file_var = f"HIBISCUS_{name}_FILE"
        path = os.environ.get(file_var)
        if path and f"HIBISCUS_{name}" not in os.environ:
            os.environ[f"HIBISCUS_{name}"] = Path(path).read_text(encoding="utf-8").strip()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HIBISCUS_", extra="ignore", frozen=False)

    env: Literal["prod", "dev", "test"] = "prod"
    version: str = "0.1.1"
    lerobot_version: str = "0.7.1"
    log_level: str = "INFO"
    log_json: bool = True

    # Public URL of the SPA (links in emails, otpauth issuer, problem type base)
    public_base_url: str = "https://robot.example.com"
    problem_type_base: str = "https://robot.example.com/problems/"
    # SPA routes used in emailed / admin-generated links. ``{token}`` is substituted. Tokens are put
    # in the URL fragment so they never reach server logs or Referer headers.
    invite_path: str = "/invite#token={token}"
    reset_password_path: str = "/reset-password#token={token}"  # noqa: S105 - URL template
    verify_email_path: str = "/verify-email#token={token}"

    # Infrastructure
    database_url: str = "postgresql+asyncpg://hibiscus:hibiscus@postgres:5432/hibiscus"
    db_pool_size: int = 10
    redis_url: str = "redis://redis:6379/0"
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    data_dir_for_disk_stats: str = "/"

    # Keys. jwt_private_key: PEM (PKCS8) Ed25519. data_key: base64 32 bytes (AES-256-GCM).
    jwt_private_key: str = ""
    jwt_previous_public_keys: list[str] = Field(default_factory=list)  # PEMs accepted for rotation
    data_key: str = ""
    cursor_secret: str = ""
    # Non-prod only (see module docstring): shared seed for the keys above, or the file they are
    # persisted in when no seed is given. Ignored in prod (keys are mandatory there).
    dev_secret: str = ""
    dev_keys_file: str = ""

    # Token lifetimes
    access_token_ttl_s: int = 15 * 60
    session_idle_ttl_s: int = 7 * 24 * 3600
    session_absolute_ttl_s: int = 30 * 24 * 3600
    # A rotated refresh token presented again within this window (concurrent tabs) gets 204 and no
    # new cookies. Outside it, it is accepted only while its successor has never been used
    # (aborted response, QC-e2e-07); otherwise the whole family is revoked (reuse detection).
    refresh_reuse_grace_s: int = 10
    mfa_token_ttl_s: int = 5 * 60
    password_reset_ttl_s: int = 30 * 60
    email_verify_ttl_s: int = 24 * 3600
    invite_ttl_s: int = 72 * 3600
    pat_default_days: int = 90

    # Cookies
    cookie_secure: bool = True
    cookie_domain: str | None = None

    # Password hashing (argon2id). Defaults = argon2-cffi RFC 9106 low-memory profile.
    argon2_time_cost: int = 3
    argon2_memory_cost_kib: int = 65536
    argon2_parallelism: int = 4
    breached_passwords_file: str | None = None  # newline-separated SHA-1 hex (HIBP format) or plain

    # Lockout / rate limits
    lockout_threshold: int = 5
    lockout_base_s: int = 60
    lockout_max_s: int = 24 * 3600
    rate_limit_enabled: bool = True
    rl_login_ip_per_min: int = 20
    rl_login_email_per_min: int = 10
    rl_forgot_per_hour: int = 5
    rl_invite_preview_per_min: int = 30
    rl_resend_per_hour: int = 5
    rl_invite_create_per_hour: int = 50
    # Password / TOTP re-checks by an already logged-in session (SEC-auth-02), per user.
    rl_reauth_per_15min: int = 10

    # Server-sent event streams (SEC-auth-03): the session / token and membership are re-checked
    # every ``sse_auth_recheck_s`` and a stream is closed after ``sse_max_lifetime_s`` (the client
    # reconnects with fresh credentials).
    sse_auth_recheck_s: float = 15.0
    sse_max_lifetime_s: float = 15 * 60

    # Client IP trust (ADR-0008): peers in these networks may set CF-Connecting-IP.
    trusted_proxy_cidrs: list[str] = Field(default_factory=list)

    # Cloudflare
    turnstile_site_key: str | None = None
    turnstile_secret_key: str | None = None
    turnstile_verify_url: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    cf_access_team_domain: str | None = None  # e.g. "myteam.cloudflareaccess.com"
    cf_access_aud: str | None = None

    # CORS (same-origin by default; dev may list the Vite origin)
    cors_origins: list[str] = Field(default_factory=list)
    max_body_bytes: int = 1024 * 1024

    # Email
    email_provider: EmailProvider = "none"
    email_from: str = "Hibiscus <no-reply@example.com>"
    email_worker_url: str | None = None  # Cloudflare Worker endpoint (provider=cloudflare)
    email_worker_secret: str = ""
    email_timeout_s: float = 10.0
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    smtp_ssl: bool = False

    # Optional routers of other packages mounted by the app factory (integration).
    extra_routers: list[str] = Field(
        default_factory=lambda: [
            "app.datasets.router",
            "app.runs.wiring",  # runs, policies, gpus, queue, jobs, models, /admin/gpus
            "app.notifications.router",  # /notifications*, /users/me/notification-channels* + dispatcher
        ]
    )

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def _cidrs_valid(cls, v: list[str]) -> list[str]:
        for c in v:
            ipaddress.ip_network(c, strict=False)
        return v

    @model_validator(mode="after")
    def _secrets(self) -> Settings:
        if self.env == "prod":
            missing = [
                n
                for n, val in (
                    ("HIBISCUS_JWT_PRIVATE_KEY", self.jwt_private_key),
                    ("HIBISCUS_DATA_KEY", self.data_key),
                    ("HIBISCUS_CURSOR_SECRET", self.cursor_secret),
                )
                if not val
            ]
            if missing:
                raise ValueError(f"missing required secrets in prod: {', '.join(missing)}")
            if self.email_provider == "cloudflare" and not (
                self.email_worker_url and self.email_worker_secret
            ):
                raise ValueError("email_provider=cloudflare needs HIBISCUS_EMAIL_WORKER_URL and _SECRET")
        elif not (self.jwt_private_key and self.data_key and self.cursor_secret):
            keys = _dev_keys(self.dev_secret, self.dev_keys_file)
            self.jwt_private_key = self.jwt_private_key or keys["jwt_private_key"]
            self.data_key = self.data_key or keys["data_key"]
            self.cursor_secret = self.cursor_secret or keys["cursor_secret"]
        if len(base64.b64decode(self.data_key)) != 32:
            raise ValueError("HIBISCUS_DATA_KEY must be base64 of exactly 32 bytes")
        return self

    @property
    def email_delivery_enabled(self) -> bool:
        return self.email_provider != "none"

    @property
    def cf_access_enabled(self) -> bool:
        return bool(self.cf_access_team_domain and self.cf_access_aud)

    def link(self, path_template: str, token: str) -> str:
        return self.public_base_url.rstrip("/") + path_template.format(token=token)


def _ed25519_pem(seed: bytes | None = None) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.from_private_bytes(seed) if seed else Ed25519PrivateKey.generate()
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


def _derive(secret: str, label: str) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"hibiscus-dev-keys/v1", info=label.encode())
    return hkdf.derive(secret.encode())


_random_keys_names = ("jwt_private_key", "data_key", "cursor_secret")


def _random_keys() -> dict[str, str]:
    return {
        "jwt_private_key": _ed25519_pem(),
        "data_key": base64.b64encode(secrets.token_bytes(32)).decode(),
        "cursor_secret": secrets.token_urlsafe(32),
    }


def _default_dev_keys_path() -> str:
    """Per-user location: ``$XDG_RUNTIME_DIR`` (0700, owned by the user) or a uid-suffixed name."""
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime and os.path.isdir(runtime) and os.stat(runtime).st_uid == os.geteuid():
        return os.path.join(runtime, "hibiscus-dev-keys.json")
    return os.path.join(tempfile.gettempdir(), f"hibiscus-dev-keys-{os.geteuid()}.json")


def _read_private_file(path: Path) -> str:
    """Read a key file only if it is a regular file (no symlink) owned by us with mode 0600 (N7).

    A file planted by another local user in a shared tmp dir would otherwise become the JWT
    signing key and the data key. Raises ``PermissionError`` for a file we must not trust.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise PermissionError("is a symlink") from e
        raise
    with os.fdopen(fd, "r", encoding="utf-8") as fh:
        st = os.fstat(fh.fileno())
        if not stat.S_ISREG(st.st_mode):
            raise PermissionError("not a regular file")
        if st.st_uid != os.geteuid():
            raise PermissionError(f"owned by uid {st.st_uid}, not {os.geteuid()}")
        if stat.S_IMODE(st.st_mode) & 0o077:
            raise PermissionError(f"mode {stat.S_IMODE(st.st_mode):o} is not 0600")
        return fh.read()


def _dev_keys(dev_secret: str, keys_file: str) -> dict[str, str]:
    """Non-prod keys shared by every process of a deployment (never per-process random)."""
    if dev_secret:
        return {
            "jwt_private_key": _ed25519_pem(_derive(dev_secret, "jwt")),
            "data_key": base64.b64encode(_derive(dev_secret, "data")).decode(),
            "cursor_secret": base64.urlsafe_b64encode(_derive(dev_secret, "cursor")).decode().rstrip("="),
        }
    path = Path(keys_file or _default_dev_keys_path())
    for _ in range(3):
        try:
            data = json.loads(_read_private_file(path))
            if isinstance(data, dict) and all(isinstance(data.get(k), str) for k in _random_keys_names):
                return {k: data[k] for k in _random_keys_names}
        except FileNotFoundError:
            pass
        except PermissionError as e:
            raise ValueError(f"refusing dev keys file {path}: {e}") from e
        except (OSError, ValueError):
            break  # unreadable / corrupt: do not overwrite it, fail loudly below
        # Write to a private temp file, then hard-link it into place: link() fails if another
        # worker won the race, in which case the next iteration reads the winner's keys.
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".hibiscus-dev-keys.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(_random_keys(), fh)
            with contextlib.suppress(FileExistsError):
                os.link(tmp, path)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
    raise ValueError(
        f"cannot load shared dev keys from {path}; set HIBISCUS_DEV_SECRET or HIBISCUS_JWT_PRIVATE_KEY"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_file_secrets()
    return Settings()


def settings_from(**overrides: Any) -> Settings:
    """Build settings with explicit overrides (tests, CLI)."""
    _load_file_secrets()
    return Settings(**overrides)
