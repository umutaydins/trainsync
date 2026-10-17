"""OAuth token storage: encrypted on write, decrypted on read."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.crypto import TokenCipher
from trainsync.db.models import OAuthToken


@dataclass(frozen=True, slots=True, repr=False)
class Tokens:
    access_token: str
    refresh_token: str
    expires_at: datetime
    scope: str

    def __repr__(self) -> str:
        return f"Tokens(expires_at={self.expires_at!r}, scope={self.scope!r})"


class TokenRepository:
    def __init__(self, session: AsyncSession, cipher: TokenCipher) -> None:
        self._session = session
        self._cipher = cipher

    async def get(self, athlete_id: int) -> Tokens | None:
        row = await self._session.scalar(
            select(OAuthToken).where(OAuthToken.athlete_id == athlete_id)
        )
        if row is None:
            return None
        return Tokens(
            access_token=self._cipher.decrypt(row.access_token_enc),
            refresh_token=self._cipher.decrypt(row.refresh_token_enc),
            expires_at=row.expires_at,
            scope=row.scope,
        )

    async def upsert(
        self, athlete_id: int, access: str, refresh: str, expires_at: datetime, scope: str
    ) -> None:
        values = {
            "access_token_enc": self._cipher.encrypt(access),
            "refresh_token_enc": self._cipher.encrypt(refresh),
            "expires_at": expires_at,
            "scope": scope,
        }
        stmt = insert(OAuthToken).values(athlete_id=athlete_id, **values)
        await self._session.execute(
            stmt.on_conflict_do_update(index_elements=[OAuthToken.athlete_id], set_=values)
        )

    async def delete(self, athlete_id: int) -> None:
        await self._session.execute(delete(OAuthToken).where(OAuthToken.athlete_id == athlete_id))


class SqlTokenStore:
    """`TokenStore` for the TokenManager: one short transaction per operation."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], cipher: TokenCipher) -> None:
        self._sessionmaker = sessionmaker
        self._cipher = cipher

    async def get(self, athlete_id: int) -> Tokens | None:
        async with self._sessionmaker() as session:
            return await TokenRepository(session, self._cipher).get(athlete_id)

    async def save(self, athlete_id: int, tokens: Tokens) -> None:
        async with self._sessionmaker.begin() as session:
            await TokenRepository(session, self._cipher).upsert(
                athlete_id,
                tokens.access_token,
                tokens.refresh_token,
                tokens.expires_at,
                tokens.scope,
            )
