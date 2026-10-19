"""`sync_runs` rows: one per backfill / incremental run, with a resumable cursor."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.strava.repository import athlete_user_id
from trainsync.modules.sync.models import SyncKind, SyncRun, SyncStatus

_OPEN = (SyncStatus.RUNNING, SyncStatus.PAUSED)


class SyncRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def open_run(
        self, athlete_id: int, kind: SyncKind, *, lock: bool = False
    ) -> SyncRun | None:
        """The latest `running` or `paused` run of this kind (optionally `FOR UPDATE`)."""
        stmt = (
            select(SyncRun)
            .where(
                SyncRun.athlete_id == athlete_id,
                SyncRun.kind == kind,
                SyncRun.status.in_(_OPEN),
            )
            .order_by(SyncRun.id.desc())
            .limit(1)
        )
        if lock:
            stmt = stmt.with_for_update()
        run: SyncRun | None = await self._session.scalar(stmt)
        return run

    async def create(
        self, athlete_id: int, kind: SyncKind, cursor: dict[str, Any], now: datetime
    ) -> SyncRun:
        run = SyncRun(
            user_id=await athlete_user_id(self._session, athlete_id),
            athlete_id=athlete_id,
            kind=kind,
            status=SyncStatus.RUNNING,
            cursor=cursor,
            pages=0,
            upserted=0,
            started_at=now,
            updated_at=now,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def checkpoint(
        self, run_id: int, cursor: dict[str, Any], upserted: int, now: datetime
    ) -> None:
        await self._session.execute(
            update(SyncRun)
            .where(SyncRun.id == run_id)
            .values(
                cursor=cursor,
                pages=SyncRun.pages + 1,
                upserted=SyncRun.upserted + upserted,
                updated_at=now,
            )
        )

    async def set_status(
        self,
        run_id: int,
        status: SyncStatus,
        now: datetime,
        *,
        error: str | None = None,
    ) -> None:
        finished = status in (SyncStatus.SUCCEEDED, SyncStatus.FAILED)
        await self._session.execute(
            update(SyncRun)
            .where(SyncRun.id == run_id)
            .values(
                status=status,
                error=error,
                updated_at=now,
                finished_at=now if finished else None,
            )
        )

    async def has_succeeded(self, athlete_id: int, kind: SyncKind) -> bool:
        found = await self._session.scalar(
            select(SyncRun.id)
            .where(
                SyncRun.athlete_id == athlete_id,
                SyncRun.kind == kind,
                SyncRun.status == SyncStatus.SUCCEEDED,
            )
            .limit(1)
        )
        return found is not None


def is_live(run: SyncRun, now: datetime, stale_after: timedelta) -> bool:
    """A `running` run whose heartbeat is recent is owned by a live worker."""
    return run.status == SyncStatus.RUNNING and now - run.updated_at < stale_after
