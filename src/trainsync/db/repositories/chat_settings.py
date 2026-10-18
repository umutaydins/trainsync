"""`chat_settings` rows: per-chat bot settings, today the language (ADR 0031)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.core.settings import BotLang
from trainsync.db.models import ChatSetting


class ChatSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lang(self, chat_id: int) -> BotLang | None:
        """The stored language, or None (the caller falls back to `BOT_LANG`)."""
        value = await self._session.scalar(
            select(ChatSetting.lang).where(ChatSetting.chat_id == chat_id)
        )
        return "tr" if value == "tr" else "en" if value == "en" else None

    async def set_lang(self, chat_id: int, lang: BotLang, now: datetime) -> None:
        stmt = insert(ChatSetting).values(chat_id=chat_id, lang=lang, updated_at=now)
        stmt = stmt.on_conflict_do_update(
            index_elements=[ChatSetting.chat_id],
            set_={"lang": stmt.excluded.lang, "updated_at": stmt.excluded.updated_at},
        )
        await self._session.execute(stmt)
