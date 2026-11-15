"""api_tokens.mfa_verified (SEC-auth-01 residual)

A PAT minted from a session that never passed 2FA must not act with owner/admin power, and
enabling 2FA revokes every PAT of the user. Existing tokens are backfilled as verified only when
they were minted after the user enabled 2FA (``createApiToken`` already required a 2FA-verified
session for such users), all others stay unverified.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-16 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_tokens",
        sa.Column("mfa_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.execute(
        "UPDATE api_tokens t SET mfa_verified = true FROM users u "
        "WHERE u.id = t.user_id AND u.totp_enabled_at IS NOT NULL AND t.created_at > u.totp_enabled_at"
    )


def downgrade() -> None:
    op.drop_column("api_tokens", "mfa_verified")
