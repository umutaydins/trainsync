"""A linked Telegram chat in the database (ADR 0036): who the worker writes to, with the user's
time zone and settings."""

from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.accounts import OWNER_ID
from trainsync.core.clock import utc_now
from trainsync.modules.auth.models import User
from trainsync.modules.chat.repository import TelegramChatRepository
from trainsync.modules.users.settings import UserSettingsRepository


async def link_chat(
    sessionmaker: async_sessionmaker[AsyncSession],
    chat_id: int,
    user_id: int = OWNER_ID,
    *,
    timezone: str | None = None,
    **settings: Any,
) -> None:
    async with sessionmaker.begin() as session:
        await TelegramChatRepository(session).link(chat_id, user_id, utc_now())
        if timezone is not None:
            await session.execute(update(User).where(User.id == user_id).values(timezone=timezone))
        if settings:
            await UserSettingsRepository(session, user_id).update(settings, utc_now())


def outcome_of(outcomes: dict[int, str], user_id: int = OWNER_ID) -> str:
    """One user's outcome of a per-user cron tick ("disabled" when they were not ticked)."""
    return outcomes.get(user_id, "disabled")
