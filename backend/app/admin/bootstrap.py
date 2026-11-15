"""Create the first platform admin and print a one-time link to set its password (CONTRACT_NOTES §4.2).

    python -m app.admin.bootstrap --email admin@example.com [--display-name "Admin"] [--ttl-minutes 60]

* Refuses when a platform admin already exists (exit code 2) — the link is strictly one-time setup.
* Creates the user with an unusable random password, ``is_platform_admin = true``, and a
  ``password_reset`` one-time token; prints ``<public_base_url>/reset-password#token=...``.
* After setting the password and logging in, the admin must enrol TOTP (mandatory for admins).
* ``--reissue`` re-prints a fresh link for the existing bootstrap admin if it never logged in.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select

from app.auth import one_time
from app.auth.passwords import PasswordHasher
from app.core.audit import AuditAction, record
from app.core.db import Database
from app.core.settings import Settings, get_settings
from app.db.models import OneTimeTokenPurpose, User


async def bootstrap(
    settings: Settings, email: str, display_name: str, ttl_minutes: int, *, reissue: bool = False
) -> tuple[int, str]:
    """Returns ``(exit_code, message)``; message is the link on success."""
    try:
        email = validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as e:
        return 1, f"invalid email: {e}"
    db = Database(settings.database_url, null_pool=True)
    try:
        async with db.session() as s:
            admins = (
                await s.execute(
                    select(func.count()).select_from(User).where(User.is_platform_admin.is_(True))
                )
            ).scalar_one()
            existing = (
                await s.execute(select(User).where(func.lower(User.email) == email))
            ).scalar_one_or_none()
            if reissue:
                if existing is None or not existing.is_platform_admin or existing.last_login_at is not None:
                    return 2, "reissue only works for a platform admin that has never logged in"
                user = existing
            else:
                if admins:
                    return 2, "a platform admin already exists; use the admin UI instead"
                if existing is not None:
                    return 2, "a user with this email already exists"
                hasher = PasswordHasher(
                    time_cost=settings.argon2_time_cost,
                    memory_cost_kib=settings.argon2_memory_cost_kib,
                    parallelism=settings.argon2_parallelism,
                )
                user = User(
                    email=email,
                    display_name=display_name,
                    password_hash=hasher.hash(secrets.token_urlsafe(48)),  # unusable until reset
                    email_verified_at=datetime.now(UTC),
                    is_platform_admin=True,
                    locale="vi",
                )
                s.add(user)
                await s.flush()
                await record(
                    AuditAction.USER_REGISTERED,
                    db=s,
                    actor=None,
                    target_type="user",
                    target_id=user.id,
                    details={"via": "bootstrap_cli", "platform_admin": True},
                )
            token, _ = await one_time.issue(
                s, user.id, OneTimeTokenPurpose.PASSWORD_RESET, ttl_minutes * 60, payload={"bootstrap": True}
            )
            await record(
                AuditAction.ADMIN_RESET_LINK_CREATED,
                db=s,
                actor=None,
                target_type="user",
                target_id=user.id,
                details={"via": "bootstrap_cli"},
            )
            await s.commit()
            return 0, settings.link(settings.reset_password_path, token)
    finally:
        await db.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.admin.bootstrap", description=__doc__.split("\n\n")[0])
    p.add_argument("--email", required=True)
    p.add_argument("--display-name", default="Admin")
    p.add_argument("--ttl-minutes", type=int, default=60, choices=range(5, 24 * 60 + 1), metavar="5..1440")
    p.add_argument(
        "--reissue", action="store_true", help="new link for a bootstrap admin that never logged in"
    )
    args = p.parse_args(argv)
    code, msg = asyncio.run(
        bootstrap(
            get_settings(),
            args.email,
            args.display_name.strip() or "Admin",
            args.ttl_minutes,
            reissue=args.reissue,
        )
    )
    if code == 0:
        print("Open this one-time link to set the admin password (then enrol 2FA):")
        print(msg)
    else:
        print(f"error: {msg}", file=sys.stderr)
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
