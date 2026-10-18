"""notifications: one row per sent notification, unique per (kind, object_id)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Rollback (ADR 0026): downgrade() restores the previous revision's schema; it drops only what
# this revision added.
reversible: bool = True


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("object_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('new_activity')", name=op.f("ck_notifications_kind")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("kind", "object_id", name=op.f("uq_notifications_kind_object_id")),
    )


def downgrade() -> None:
    op.drop_table("notifications")
