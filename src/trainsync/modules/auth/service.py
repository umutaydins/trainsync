"""Registration, sign-in, sessions, invites and resets (ADR 0034).

Functions take the sessionmaker and open their own transaction, so a router stays a thin
mapping from HTTP to these calls. Times come from the injected clock.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.clock import Clock
from trainsync.core.security import (
    UNUSABLE_HASH,
    hash_password,
    new_token,
    normal_email,
    password_problem,
    token_hash,
    verify_password,
)
from trainsync.core.settings import Settings
from trainsync.modules.auth.errors import (
    AuthError,
    EmailTakenError,
    InvalidCredentialsError,
    InvalidTokenError,
    RateLimitedError,
    RegistrationClosedError,
    WeakPasswordError,
)
from trainsync.modules.auth.limits import AuthLimiter
from trainsync.modules.auth.models import AuthSession, Invite, User, UserRole
from trainsync.modules.auth.repository import (
    InviteRepository,
    ResetRepository,
    SessionRepository,
    UserRepository,
)

Sessionmaker = async_sessionmaker[AsyncSession]
USER_AGENT_MAX = 200
DISPLAY_NAME_MAX = 100
INVALID_LOGIN = "invalid email or password"


@dataclass(frozen=True, slots=True)
class Principal:
    """Who a request acts as. `session_id` is set for a signed-in session, None for an API key."""

    user_id: int
    role: UserRole
    timezone: str
    session_id: int | None = None

    @property
    def is_owner(self) -> bool:
        return self.role is UserRole.OWNER


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str  # shown once; only its hash is stored
    expires_at: datetime
    user: User


def valid_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise AuthError(f"unknown time zone {name!r}") from exc
    return name


def _check_password(password: str) -> None:
    problem = password_problem(password)
    if problem:
        raise WeakPasswordError(problem)


def _display_name(name: str | None, email: str) -> str:
    chosen = (name or "").strip() or email.split("@", 1)[0]
    return chosen[:DISPLAY_NAME_MAX]


# ---------------------------------------------------------------- registration


async def register(
    db: Sessionmaker,
    settings: Settings,
    clock: Clock,
    limiter: AuthLimiter,
    *,
    email: str,
    password: str,
    display_name: str | None,
    timezone: str | None,
    invite_code: str | None,
    address: str,
) -> User:
    if settings.registration_mode == "closed":
        raise RegistrationClosedError("registration is closed")
    retry = await limiter.register_blocked(address)
    if retry is not None:
        raise RateLimitedError("too many registrations; try again later", retry_after=retry)
    email = normal_email(email)
    _check_password(password)
    zone = valid_timezone(timezone or settings.checkin_tz)
    password_hash = await hash_password(password)
    now = clock()
    async with db.begin() as session:
        invite = await _take_invite(session, settings, invite_code, now)
        users = UserRepository(session)
        if await users.email_taken(email):
            raise EmailTakenError("an account with this email already exists")
        user = await users.add(
            email=email,
            password_hash=password_hash,
            display_name=_display_name(display_name, email),
            timezone=zone,
            role=UserRole.USER,
        )
        if invite is not None:
            await InviteRepository(session).mark_used(invite.id, user.id, now)
    await limiter.registered(address)
    return user


async def _take_invite(
    session: AsyncSession, settings: Settings, code: str | None, now: datetime
) -> Invite | None:
    if settings.registration_mode == "open":
        return None
    if not code:
        raise InvalidTokenError("an invite code is required")
    invite = await InviteRepository(session).usable_for_update(token_hash(code.strip()), now)
    if invite is None:
        raise InvalidTokenError("the invite code is invalid, used or expired")
    return invite


# ---------------------------------------------------------------- sessions


async def login(
    db: Sessionmaker,
    settings: Settings,
    clock: Clock,
    limiter: AuthLimiter,
    *,
    email: str,
    password: str,
    user_agent: str | None,
    address: str,
) -> IssuedSession:
    email = normal_email(email)
    retry = await limiter.login_blocked(email, address)
    if retry is not None:
        raise RateLimitedError("too many failed sign-ins; try again later", retry_after=retry)
    async with db() as session:
        user = await UserRepository(session).by_email(email)
    if not await verify_password(password, user.password_hash if user else None) or user is None:
        await limiter.login_failed(email, address)
        raise InvalidCredentialsError(INVALID_LOGIN)
    await limiter.login_succeeded(email)
    return await issue_session(db, settings, clock, user, user_agent)


async def issue_session(
    db: Sessionmaker, settings: Settings, clock: Clock, user: User, user_agent: str | None
) -> IssuedSession:
    now = clock()
    token = new_token()
    expires_at = now + timedelta(days=settings.session_ttl_days)
    async with db.begin() as session:
        await SessionRepository(session).add(
            user_id=user.id,
            token_hash=token_hash(token),
            user_agent=(user_agent or "")[:USER_AGENT_MAX] or None,
            now=now,
            expires_at=expires_at,
        )
    return IssuedSession(token, expires_at, user)


def _slid_expiry(row: AuthSession, settings: Settings, now: datetime) -> datetime:
    cap = row.created_at + timedelta(days=settings.session_max_age_days)
    return min(now + timedelta(days=settings.session_ttl_days), cap)


async def authenticate(
    db: Sessionmaker, settings: Settings, clock: Clock, token: str
) -> Principal | None:
    """The principal of a live session token; slides its expiry (written at most every
    `SESSION_TOUCH_INTERVAL_S`)."""
    now = clock()
    async with db.begin() as session:
        sessions = SessionRepository(session)
        found = await sessions.live(token_hash(token), now)
        if found is None:
            return None
        row, user = found
        if (now - row.last_seen_at).total_seconds() >= settings.session_touch_interval_s:
            await sessions.touch(row.id, now, _slid_expiry(row, settings, now))
    return Principal(user.id, UserRole(user.role), user.timezone, row.id)


async def logout(db: Sessionmaker, clock: Clock, principal: Principal) -> None:
    if principal.session_id is None:
        return
    async with db.begin() as session:
        await SessionRepository(session).revoke(principal.user_id, principal.session_id, clock())


async def sessions_of(db: Sessionmaker, clock: Clock, user_id: int) -> list[AuthSession]:
    async with db() as session:
        return list(await SessionRepository(session).for_user(user_id, clock()))


async def revoke_session(db: Sessionmaker, clock: Clock, user_id: int, session_id: int) -> bool:
    async with db.begin() as session:
        return await SessionRepository(session).revoke(user_id, session_id, clock())


async def change_password(
    db: Sessionmaker, clock: Clock, principal: Principal, *, current: str, new: str
) -> None:
    """Checks the current password; every other session of the user is revoked."""
    _check_password(new)
    async with db() as session:
        user = await UserRepository(session).by_id(principal.user_id)
    if user is None or not await verify_password(current, user.password_hash):
        raise InvalidCredentialsError("the current password is wrong")
    new_hash = await hash_password(new)
    async with db.begin() as session:
        await UserRepository(session).set_password(user.id, new_hash)
        await SessionRepository(session).revoke_all(user.id, clock(), keep=principal.session_id)


# ---------------------------------------------------------------- invites and resets


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
    _check_password(new)
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
    _check_password(new)
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
            display_name=_display_name(display_name, email),
            timezone=settings.checkin_tz,
            role=UserRole.OWNER,
        )
