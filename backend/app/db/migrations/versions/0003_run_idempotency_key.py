"""atomic Idempotency-Key for createRun (QC-backend-06, SEC-auth-05)

Adds ``runs.idempotency_key`` and a partial unique index on
``(workspace_id, created_by, idempotency_key)``: concurrent retries of ``POST /runs`` with the same
key can no longer both insert a run (the loser hits the index and replays the winner's run), and
keys are scoped per user *and* workspace. Replaces the previous Redis check-then-set.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-15 23:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("idempotency_key", sa.String(length=64), nullable=True))
    op.create_index(
        "uq_runs_idempotency_key",
        "runs",
        ["workspace_id", "created_by", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_runs_idempotency_key",
        table_name="runs",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_column("runs", "idempotency_key")
