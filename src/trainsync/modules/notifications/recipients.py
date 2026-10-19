"""Who the worker writes to (ADR 0036): every user with a linked chat, with their settings.

The worker reads them at send time, so a `/lang`, `/swear` or settings change reaches the next
reminder, check-in or notification without a restart. `context()` is the user's voice and
clock for the send (`using_context`).
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.settings import BotLang, Settings
from trainsync.modules.auth.models import User
from trainsync.modules.chat.models import TelegramChat
from trainsync.modules.coach.context import UserContext
from trainsync.modules.users.models import UserSettings
from trainsync.modules.users.settings import FIELDS, Effective, effective


@dataclass(frozen=True, slots=True)
class Recipient:
    user_id: int
    chat_id: int
    settings: Effective  # every value resolved: what the schedules use
    chosen: frozenset[str] = frozenset()  # the settings the user set themselves

    def context(self) -> UserContext:
        """The voice for a send. Only what the user chose overrides the worker's own defaults
        (the same environment as the API's), like the bot does (`chat.links`)."""
        values = self.settings

        def pick[T](name: str, value: T) -> T | None:
            return value if name in self.chosen else None

        return UserContext(
            user_id=self.user_id,
            tone=pick("tone", values.tone),
            lang=pick("lang", values.lang),
            savage=values.savage if self.chosen & {"tone", "intensity"} else None,
            profanity=pick("profanity", values.profanity),
            emergency_number=pick("country", values.emergency_number),
            timezone=values.timezone,
            workout_reminder_time=pick("workout_reminder_time", values.workout_reminder_time),
            sugar_limit_g=pick("sugar_limit_g", values.sugar_limit_g),
        )


async def _load(session: AsyncSession, settings: Settings, user_id: int | None) -> list[Recipient]:
    stmt = (
        select(User, TelegramChat.chat_id, UserSettings)
        .join(TelegramChat, TelegramChat.user_id == User.id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(User.deleted_at.is_(None))
        .order_by(User.id)
    )
    if user_id is not None:
        stmt = stmt.where(User.id == user_id)
    rows = await session.execute(stmt)
    return [
        Recipient(
            user.id,
            chat_id,
            effective(user.id, user.timezone, stored, settings),
            frozenset(n for n in FIELDS if stored is not None and getattr(stored, n) is not None),
        )
        for user, chat_id, stored in rows.tuples()
    ]


async def recipients(
    sessionmaker: async_sessionmaker[AsyncSession], settings: Settings
) -> list[Recipient]:
    async with sessionmaker() as session:
        return await _load(session, settings, None)


async def recipient(
    sessionmaker: async_sessionmaker[AsyncSession], settings: Settings, user_id: int
) -> Recipient | None:
    """The user's linked chat with their settings, or None (no chat linked, or deleted)."""
    async with sessionmaker() as session:
        found = await _load(session, settings, user_id)
    return found[0] if found else None


async def chat_lang(
    sessionmaker: async_sessionmaker[AsyncSession], settings: Settings, chat: int | str | None
) -> BotLang | None:
    """The language of whoever a chat is linked to (the owner's operations chat for alerts),
    or None for an unlinked chat (then `BOT_LANG`)."""
    try:
        chat_id = int(chat) if chat is not None else None
    except ValueError:
        return None
    if chat_id is None:
        return None
    async with sessionmaker() as session:
        user_id = await session.scalar(
            select(TelegramChat.user_id).where(TelegramChat.chat_id == chat_id)
        )
    if user_id is None:
        return None
    found = await recipient(sessionmaker, settings, int(user_id))
    return found.settings.lang if found else None
