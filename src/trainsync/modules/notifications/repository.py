"""`notifications` rows: the idempotency guard for outgoing notifications (ADR 0012), per user
(ADR 0035): the same kind and object id can be sent once to each user."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.notifications.models import Notification, NotificationKind


class NotificationRepository:
    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    async def claim(self, kind: NotificationKind, object_id: int, now: datetime) -> bool:
        """Insert the row; `False` if this notification was already claimed (sent or sending)."""
        stmt = (
            insert(Notification)
            .values(user_id=self._user_id, kind=kind.value, object_id=object_id, sent_at=now)
            .on_conflict_do_nothing(
                index_elements=[Notification.user_id, Notification.kind, Notification.object_id]
            )
            .returning(Notification.id)
        )
        return await self._session.scalar(stmt) is not None

    async def release(self, kind: NotificationKind, object_id: int) -> None:
        """Undo a claim after a failed send, so a retry can claim it again."""
        await self._session.execute(
            delete(Notification).where(
                Notification.user_id == self._user_id,
                Notification.kind == kind.value,
                Notification.object_id == object_id,
            )
        )

    async def sent_at(self, kind: NotificationKind, object_id: int) -> datetime | None:
        """When this notification was claimed, or None if it never was."""
        return await self._session.scalar(
            select(Notification.sent_at).where(
                Notification.user_id == self._user_id,
                Notification.kind == kind.value,
                Notification.object_id == object_id,
            )
        )
