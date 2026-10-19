"""Linked chats and one-time link codes (ADR 0036)."""

import secrets
from datetime import datetime

from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.chat.models import TelegramChat

# Unambiguous: no 0/O, 1/I/L.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 8
CODE_KEY = "telegram:link"


class TelegramChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def by_chat(self, chat_id: int) -> TelegramChat | None:
        return await self._session.get(TelegramChat, chat_id)

    async def by_user(self, user_id: int) -> TelegramChat | None:
        return await self._session.scalar(
            select(TelegramChat).where(TelegramChat.user_id == user_id)
        )

    async def link(self, chat_id: int, user_id: int, now: datetime) -> None:
        """Bind the chat to the user; the user's previous chat (if any) is unlinked."""
        await self._session.execute(
            delete(TelegramChat).where(
                TelegramChat.user_id == user_id, TelegramChat.chat_id != chat_id
            )
        )
        stmt = insert(TelegramChat).values(chat_id=chat_id, user_id=user_id, linked_at=now)
        await self._session.execute(
            stmt.on_conflict_do_update(
                index_elements=[TelegramChat.chat_id],
                set_={"user_id": stmt.excluded.user_id, "linked_at": now},
            )
        )

    async def unlink_chat(self, chat_id: int) -> bool:
        result = await self._session.execute(
            delete(TelegramChat)
            .where(TelegramChat.chat_id == chat_id)
            .returning(TelegramChat.chat_id)
        )
        return result.first() is not None

    async def unlink_user(self, user_id: int) -> bool:
        result = await self._session.execute(
            delete(TelegramChat)
            .where(TelegramChat.user_id == user_id)
            .returning(TelegramChat.chat_id)
        )
        return result.first() is not None

    async def linked(self) -> list[TelegramChat]:
        rows = await self._session.scalars(select(TelegramChat).order_by(TelegramChat.user_id))
        return list(rows)


class LinkCodes:
    """`/link CODE` codes in Redis: one per issue, deleted on use, expiring on their own."""

    def __init__(self, redis: Redis, ttl_s: int) -> None:
        self._redis = redis
        self._ttl_s = ttl_s

    async def issue(self, user_id: int) -> str:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        await self._redis.set(f"{CODE_KEY}:{code}", str(user_id), ex=self._ttl_s)
        return code

    async def redeem(self, code: str) -> int | None:
        """The user the code was issued for, once; None when unknown, used or expired."""
        value = await self._redis.getdel(f"{CODE_KEY}:{code.strip().upper()}")
        if value is None:
            return None
        return int(value.decode() if isinstance(value, bytes) else value)
