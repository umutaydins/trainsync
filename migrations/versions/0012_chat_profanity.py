"""chat_settings.profanity: the level a chat chose with /swear (ADR 0032)

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Rollback (ADR 0026): downgrade() drops the column (chats fall back to BOT_PROFANITY) and the
# rows that only held a profanity choice; every chosen language is kept.
reversible: bool = True


def upgrade() -> None:
    op.add_column("chat_settings", sa.Column("profanity", sa.String(length=8), nullable=True))
    op.create_check_constraint(
        op.f("ck_chat_settings_profanity"), "chat_settings", "profanity IN ('roast', 'max')"
    )
    # A chat can now choose a profanity level without ever choosing a language.
    op.alter_column("chat_settings", "lang", existing_type=sa.String(length=2), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM chat_settings WHERE lang IS NULL")
    op.alter_column("chat_settings", "lang", existing_type=sa.String(length=2), nullable=False)
    op.drop_constraint(op.f("ck_chat_settings_profanity"), "chat_settings", type_="check")
    op.drop_column("chat_settings", "profanity")
