"""`chat_settings` rows: per-chat bot settings, the language (ADR 0031) and the profanity level
(ADR 0032). A null column means "the default" (`BOT_LANG`, `BOT_PROFANITY`)."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.core.settings import BotLang, BotProfanity
from trainsync.modules.chat.models import ChatSetting


@dataclass(frozen=True, slots=True)
class ChatPrefs:
    lang: BotLang | None = None
    profanity: BotProfanity | None = None


def _lang(value: str | None) -> BotLang | None:
    return "tr" if value == "tr" else "en" if value == "en" else None


def _profanity(value: str | None) -> BotProfanity | None:
    return "max" if value == "max" else "roast" if value == "roast" else None


class ChatSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, chat_id: int) -> ChatPrefs:
        """The stored choices; an empty `ChatPrefs` when the chat never chose anything."""
        row = (
            await self._session.execute(
                select(ChatSetting.lang, ChatSetting.profanity).where(
                    ChatSetting.chat_id == chat_id
                )
            )
        ).first()
        if row is None:
            return ChatPrefs()
        return ChatPrefs(_lang(row.lang), _profanity(row.profanity))

    async def lang(self, chat_id: int) -> BotLang | None:
        """The stored language, or None (the caller falls back to `BOT_LANG`)."""
        return (await self.get(chat_id)).lang

    async def set(
        self,
        chat_id: int,
        now: datetime,
        *,
        lang: BotLang | None = None,
        profanity: BotProfanity | None = None,
    ) -> ChatPrefs:
        """Store the given choices; a None argument keeps what is stored. Returns the row."""
        values: dict[str, object] = {"updated_at": now}
        if lang is not None:
            values["lang"] = lang
        if profanity is not None:
            values["profanity"] = profanity
        stmt = insert(ChatSetting).values(chat_id=chat_id, **values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[ChatSetting.chat_id],
            set_={key: stmt.excluded[key] for key in values},
        )
        await self._session.execute(stmt)
        return await self.get(chat_id)

    async def set_lang(self, chat_id: int, lang: BotLang, now: datetime) -> None:
        await self.set(chat_id, now, lang=lang)
