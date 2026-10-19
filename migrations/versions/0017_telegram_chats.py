"""telegram_chats; per-chat settings move into user_settings (P8.4, P8.5, ADR 0036)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-19

The bootstrap chat (`TELEGRAM_NOTIFY_CHAT_ID`, else the first of `TELEGRAM_ALLOWED_CHAT_IDS`) is
linked to the owner, and the language and profanity that chat chose become the owner's settings.
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Rollback (ADR 0026): downgrade() recreates chat_settings from the linked chats' user settings.
reversible: bool = True


def _bootstrap_chat() -> int | None:
    notify = os.environ.get("TELEGRAM_NOTIFY_CHAT_ID", "").strip()
    allowed = [c.strip() for c in os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",")]
    first = notify or next((c for c in allowed if c), "")
    return int(first) if first else None


def upgrade() -> None:
    op.create_table(
        "telegram_chats",
        sa.Column("chat_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "linked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_telegram_chats_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("chat_id", name=op.f("pk_telegram_chats")),
        sa.UniqueConstraint("user_id", name=op.f("uq_telegram_chats_user_id")),
    )
    conn = op.get_bind()
    owner = conn.execute(sa.text("SELECT id FROM users WHERE role = 'owner'")).scalar()
    chat = _bootstrap_chat()
    if owner is not None and chat is not None:
        conn.execute(
            sa.text(
                "INSERT INTO telegram_chats (chat_id, user_id) VALUES (:chat, :owner)"
                " ON CONFLICT DO NOTHING"
            ),
            {"chat": chat, "owner": owner},
        )
    if owner is not None:
        # The owner's choices: the bootstrap chat's row, else the most recent one.
        conn.execute(
            sa.text(
                "INSERT INTO user_settings (user_id, lang, profanity)"
                " SELECT :owner, lang, profanity FROM chat_settings"
                " ORDER BY (chat_id = :chat) DESC, updated_at DESC LIMIT 1"
                " ON CONFLICT (user_id) DO NOTHING"
            ),
            {"owner": owner, "chat": chat},
        )
    op.drop_table("chat_settings")


def downgrade() -> None:
    op.create_table(
        "chat_settings",
        sa.Column("chat_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("lang", sa.String(length=2), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("profanity", sa.String(length=8), nullable=True),
        sa.CheckConstraint("lang IN ('en', 'tr')", name=op.f("ck_chat_settings_lang")),
        sa.CheckConstraint(
            "profanity IN ('roast', 'max')", name=op.f("ck_chat_settings_profanity")
        ),
        sa.PrimaryKeyConstraint("chat_id", name=op.f("pk_chat_settings")),
    )
    op.execute(
        "INSERT INTO chat_settings (chat_id, lang, profanity)"
        " SELECT t.chat_id, s.lang, s.profanity FROM telegram_chats t"
        " JOIN user_settings s ON s.user_id = t.user_id"
        " WHERE s.lang IS NOT NULL OR s.profanity IS NOT NULL"
    )
    op.drop_table("telegram_chats")
