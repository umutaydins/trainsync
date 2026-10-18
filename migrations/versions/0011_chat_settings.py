"""chat_settings: the language a chat chose with /lang (ADR 0031)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Rollback (ADR 0026): downgrade() drops the table; chats fall back to BOT_LANG.
reversible: bool = True


def upgrade() -> None:
    op.create_table(
        "chat_settings",
        sa.Column("chat_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("lang", sa.String(length=2), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("lang IN ('en', 'tr')", name=op.f("ck_chat_settings_lang")),
        sa.PrimaryKeyConstraint("chat_id", name=op.f("pk_chat_settings")),
    )


def downgrade() -> None:
    op.drop_table("chat_settings")
