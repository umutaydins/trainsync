"""Account, session, invite and reset rows. Tokens are looked up by their SHA-256; deleted
users (`deleted_at`) are invisible to every lookup except the purge."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.auth.models import AuthSession, Invite, PasswordReset, User, UserRole


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self, *, email: str, password_hash: str, display_name: str, timezone: str, role: UserRole
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            timezone=timezone,
            role=role.value,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def by_id(self, user_id: int) -> User | None:
        return await self._session.scalar(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )

    async def by_email(self, email: str) -> User | None:
        return await self._session.scalar(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )

    async def email_taken(self, email: str) -> bool:
        """Deleted-but-not-purged accounts still hold their email."""
        return await self._session.scalar(select(User.id).where(User.email == email)) is not None

    async def owner(self) -> User | None:
        return await self._session.scalar(
            select(User).where(User.role == UserRole.OWNER.value, User.deleted_at.is_(None))
        )

    async def active(self) -> Sequence[User]:
        rows = await self._session.scalars(
            select(User).where(User.deleted_at.is_(None)).order_by(User.id)
        )
        return rows.all()

    async def update_profile(
        self, user_id: int, *, display_name: str | None, timezone: str | None
    ) -> None:
        values: dict[str, str] = {}
        if display_name is not None:
            values["display_name"] = display_name.strip()
        if timezone is not None:
            values["timezone"] = timezone
        if values:
            await self._session.execute(update(User).where(User.id == user_id).values(**values))

    async def set_password(self, user_id: int, password_hash: str) -> None:
        await self._session.execute(
            update(User).where(User.id == user_id).values(password_hash=password_hash)
        )

    async def mark_deleted(self, user_id: int, now: datetime) -> None:
        await self._session.execute(update(User).where(User.id == user_id).values(deleted_at=now))

    async def deleted_ids(self) -> list[int]:
        rows = await self._session.scalars(select(User.id).where(User.deleted_at.is_not(None)))
        return list(rows)


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        user_id: int,
        token_hash: bytes,
        user_agent: str | None,
        now: datetime,
        expires_at: datetime,
    ) -> AuthSession:
        row = AuthSession(
            user_id=user_id,
            token_hash=token_hash,
            user_agent=user_agent,
            created_at=now,
            last_seen_at=now,
            expires_at=expires_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def live(self, token_hash: bytes, now: datetime) -> tuple[AuthSession, User] | None:
        """The session and its user: not revoked, not expired, user not deleted."""
        row = (
            await self._session.execute(
                select(AuthSession, User)
                .join(User, User.id == AuthSession.user_id)
                .where(
                    AuthSession.token_hash == token_hash,
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now,
                    User.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        return None if row is None else (row[0], row[1])

    async def touch(self, session_id: int, now: datetime, expires_at: datetime) -> None:
        await self._session.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id)
            .values(last_seen_at=now, expires_at=expires_at)
        )

    async def for_user(self, user_id: int, now: datetime) -> Sequence[AuthSession]:
        rows = await self._session.scalars(
            select(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
            .order_by(AuthSession.last_seen_at.desc())
        )
        return rows.all()

    async def revoke(self, user_id: int, session_id: int, now: datetime) -> bool:
        result = await self._session.execute(
            update(AuthSession)
            .where(
                AuthSession.id == session_id,
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
            .returning(AuthSession.id)
        )
        return result.first() is not None

    async def revoke_all(self, user_id: int, now: datetime, *, keep: int | None = None) -> None:
        stmt = update(AuthSession).where(
            AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
        )
        if keep is not None:
            stmt = stmt.where(AuthSession.id != keep)
        await self._session.execute(stmt.values(revoked_at=now))


class InviteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self, *, code_hash: bytes, created_by: int | None, note: str | None, expires_at: datetime
    ) -> Invite:
        row = Invite(code_hash=code_hash, created_by=created_by, note=note, expires_at=expires_at)
        self._session.add(row)
        await self._session.flush()
        return row

    async def usable_for_update(self, code_hash: bytes, now: datetime) -> Invite | None:
        """Unused, unrevoked, unexpired; locked so two registrations cannot both use it."""
        return await self._session.scalar(
            select(Invite)
            .where(
                Invite.code_hash == code_hash,
                Invite.used_at.is_(None),
                Invite.revoked_at.is_(None),
                Invite.expires_at > now,
            )
            .with_for_update()
        )

    async def mark_used(self, invite_id: int, user_id: int, now: datetime) -> None:
        await self._session.execute(
            update(Invite).where(Invite.id == invite_id).values(used_at=now, used_by=user_id)
        )

    async def all(self) -> Sequence[Invite]:
        rows = await self._session.scalars(select(Invite).order_by(Invite.id.desc()))
        return rows.all()

    async def revoke(self, invite_id: int, now: datetime) -> bool:
        result = await self._session.execute(
            update(Invite)
            .where(Invite.id == invite_id, Invite.used_at.is_(None), Invite.revoked_at.is_(None))
            .values(revoked_at=now)
            .returning(Invite.id)
        )
        return result.first() is not None


class ResetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, user_id: int, token_hash: bytes, expires_at: datetime) -> PasswordReset:
        row = PasswordReset(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(row)
        await self._session.flush()
        return row

    async def usable_for_update(self, token_hash: bytes, now: datetime) -> PasswordReset | None:
        return await self._session.scalar(
            select(PasswordReset)
            .where(
                PasswordReset.token_hash == token_hash,
                PasswordReset.used_at.is_(None),
                PasswordReset.expires_at > now,
            )
            .with_for_update()
        )

    async def mark_used(self, reset_id: int, now: datetime) -> None:
        await self._session.execute(
            update(PasswordReset).where(PasswordReset.id == reset_id).values(used_at=now)
        )
