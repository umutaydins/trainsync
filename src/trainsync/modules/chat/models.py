"""Per-chat settings: language and profanity (ADR 0031, 0032)."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from trainsync.core.orm import Base, utc_timestamp


class ChatSetting(Base):
    """Per-chat bot settings: the language chosen with `/lang` (ADR 0031) and the profanity
    level chosen with `/swear` (ADR 0032). Null = the default (`BOT_LANG`, `BOT_PROFANITY`)."""

    __tablename__ = "chat_settings"
    __table_args__ = (
        CheckConstraint("lang IN ('en', 'tr')", name="lang"),
        CheckConstraint("profanity IN ('roast', 'max')", name="profanity"),
    )

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    lang: Mapped[str | None] = mapped_column(String(2))
    profanity: Mapped[str | None] = mapped_column(String(8))
    updated_at: Mapped[datetime] = utc_timestamp(default_now=True)
