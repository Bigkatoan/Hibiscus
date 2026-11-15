"""notification delivery tracking (CR-BE-N1)

Adds ``notifications.dispatched_at`` (fan-out marker for the API dispatcher) and the
``notification_deliveries`` table (one row per notification x external channel: status, attempts,
backoff, last error). Existing notifications are marked dispatched so upgrading never replays
history to external channels.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-15 22:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE notifications SET dispatched_at = created_at WHERE dispatched_at IS NULL")
    op.create_index(
        "ix_notifications_undispatched",
        "notifications",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("dispatched_at IS NULL"),
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "next_attempt_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')",
            name=op.f("ck_notification_deliveries_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            name=op.f("fk_notification_deliveries_notification_id_notifications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["notification_channels.id"],
            name=op.f("fk_notification_deliveries_channel_id_notification_channels"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_deliveries")),
        sa.UniqueConstraint(
            "notification_id",
            "channel_id",
            name=op.f("uq_notification_deliveries_notification_id_channel_id"),
        ),
    )
    op.create_index(
        op.f("ix_notification_deliveries_channel_id"), "notification_deliveries", ["channel_id"], unique=False
    )
    op.create_index(
        "ix_notification_deliveries_due",
        "notification_deliveries",
        ["next_attempt_at"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_deliveries_due",
        table_name="notification_deliveries",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index(op.f("ix_notification_deliveries_channel_id"), table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_index(
        "ix_notifications_undispatched",
        table_name="notifications",
        postgresql_where=sa.text("dispatched_at IS NULL"),
    )
    op.drop_column("notifications", "dispatched_at")
