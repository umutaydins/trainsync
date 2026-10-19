"""Invites, password resets and the owner account (ADR 0034): one-time tokens handed out by the
owner, and owner tooling. Re-exported by `service`."""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.clock import Clock
from trainsync.core.security import (
    UNUSABLE_HASH,
    hash_password,
    new_token,
    normal_email,
    password_problem,
    token_hash,
)
from trainsync.core.settings import Settings
from trainsync.modules.auth.errors import InvalidTokenError, WeakPasswordError
from trainsync.modules.auth.models import Invite, User, UserRole
from trainsync.modules.auth.repository import (
    InviteRepository,
    ResetRepository,
    SessionRepository,
    UserRepository,
)

Sessionmaker = async_sessionmaker[AsyncSession]
DISPLAY_NAME_MAX = 100


def check_password(password: str) -> None:
    problem = password_problem(password)
    if problem:
        raise WeakPasswordError(problem)


def default_display_name(name: str | None, email: str) -> str:
    chosen = (name or "").strip() or email.split("@", 1)[0]
    return chosen[:DISPLAY_NAME_MAX]


async def create_invite(
    db: Sessionmaker, settings: Settings, clock: Clock, *, created_by: int | None, note: str | None
) -> tuple[Invite, str]:
    code = new_token()
    expires_at = clock() + timedelta(days=settings.invite_ttl_days)
    async with db.begin() as session:
        invite = await InviteRepository(session).add(
            code_hash=token_hash(code), created_by=created_by, note=note, expires_at=expires_at
        )
    return invite, code


async def create_reset(
    db: Sessionmaker, settings: Settings, clock: Clock, user_id: int
) -> tuple[str, datetime]:
    """A one-time reset token for the user (the owner hands out the link)."""
    token = new_token()
    expires_at = clock() + timedelta(minutes=settings.reset_ttl_minutes)
    async with db.begin() as session:
        if await UserRepository(session).by_id(user_id) is None:
            raise InvalidTokenError("no such user")
        await ResetRepository(session).add(
            user_id=user_id, token_hash=token_hash(token), expires_at=expires_at
        )
    return token, expires_at


async def reset_password(db: Sessionmaker, clock: Clock, *, token: str, new: str) -> None:
    check_password(new)
    new_hash = await hash_password(new)
    now = clock()
    async with db.begin() as session:
        resets = ResetRepository(session)
        reset = await resets.usable_for_update(token_hash(token), now)
        if reset is None:
            raise InvalidTokenError("the reset link is invalid, used or expired")
        await UserRepository(session).set_password(reset.user_id, new_hash)
        await resets.mark_used(reset.id, now)
        await SessionRepository(session).revoke_all(reset.user_id, now)


async def set_password(db: Sessionmaker, clock: Clock, user_id: int, new: str) -> None:
    """Owner tooling (`scripts/owner.py set-password`): no current password; all sessions end."""
    check_password(new)
    new_hash = await hash_password(new)
    async with db.begin() as session:
        await UserRepository(session).set_password(user_id, new_hash)
        await SessionRepository(session).revoke_all(user_id, clock())


async def ensure_owner(
    db: Sessionmaker, settings: Settings, *, email: str, display_name: str | None = None
) -> User:
    """The owner account, created with an unusable password if missing (owner CLI, tests)."""
    email = normal_email(email)
    async with db.begin() as session:
        users = UserRepository(session)
        owner = await users.owner()
        if owner is not None:
            return owner
        return await users.add(
            email=email,
            password_hash=UNUSABLE_HASH,
            display_name=default_display_name(display_name, email),
            timezone=settings.checkin_tz,
            role=UserRole.OWNER,
        )
