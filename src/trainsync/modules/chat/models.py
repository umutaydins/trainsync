"""Linked Telegram chats (ADR 0036): one chat per user, one user per chat."""

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from trainsync.core.orm import Base, utc_timestamp


class TelegramChat(Base):
    """A chat bound to an account with `/link CODE`. The bot answers only linked chats."""

    __tablename__ = "telegram_chats"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    linked_at: Mapped[datetime] = utc_timestamp(default_now=True)
