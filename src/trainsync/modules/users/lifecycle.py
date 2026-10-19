"""Leaving trainsync (ADR 0037): deletion answers at once, the purge job does the rest.

`delete_account` marks the account deleted, ends every session, unlinks Telegram and stops
syncing; `purge_user` (worker) revokes the app at Strava while the tokens still exist, then
deletes the user row, and with it every row of the user (`ON DELETE CASCADE`).
"""

from datetime import datetime
from typing import Any

from arq.worker import func
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.logging import get_logger
from trainsync.modules.auth.models import User
from trainsync.modules.auth.repository import SessionRepository, UserRepository
from trainsync.modules.chat.models import TelegramChat
from trainsync.modules.strava.repository import AthleteRepository
from trainsync.modules.sync.context import job_log_context, worker_context
from trainsync.modules.sync.disconnect import Deauthorizer, revoke_at_strava

log = get_logger(__name__)


async def delete_account(session: AsyncSession, user_id: int, now: datetime) -> None:
    await UserRepository(session).mark_deleted(user_id, now)
    await SessionRepository(session).revoke_all(user_id, now)
    await session.execute(delete(TelegramChat).where(TelegramChat.user_id == user_id))
    athletes = AthleteRepository(session)
    athlete = await athletes.for_user(user_id)
    if athlete is not None:
        await athletes.set_active(athlete.id, active=False)


async def purge(
    sessionmaker: async_sessionmaker[AsyncSession], strava: Deauthorizer, user_id: int
) -> str:
    """Outcome: purged / not_deleted (the account is not marked deleted: nothing happens)."""
    async with sessionmaker() as session:
        deleted = await session.scalar(
            select(User.id).where(User.id == user_id, User.deleted_at.is_not(None))
        )
        athlete = await AthleteRepository(session).for_user(user_id) if deleted else None
    if deleted is None:
        return "not_deleted"
    if athlete is not None:
        await revoke_at_strava(strava, athlete.id)
    async with sessionmaker.begin() as session:
        await session.execute(delete(User).where(User.id == user_id))
    log.info("user_purged", user_id=user_id)
    return "purged"


async def purge_user(ctx: dict[str, Any], user_id: int) -> str:
    with job_log_context(ctx, "purge_user", user_id=user_id):
        wc = worker_context(ctx)
        return await purge(wc.sessionmaker, wc.strava, user_id)


purge_user_job = func(purge_user, name="purge_user", max_tries=5)
