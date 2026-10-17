from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.db.models import (
    Activity,
    Athlete,
    OAuthToken,
    SyncKind,
    SyncRun,
    SyncStatus,
    WebhookEvent,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _activity(athlete_id: int, strava_activity_id: int) -> Activity:
    return Activity(
        strava_activity_id=strava_activity_id,
        athlete_id=athlete_id,
        name="Morning Run",
        sport_type="Run",
        start_date=NOW,
        distance_m=10_000.0,
        moving_time_s=3000,
        elapsed_time_s=3100,
        elevation_gain_m=50.0,
        raw={"id": strava_activity_id},
    )


async def _athlete(session: AsyncSession, strava_athlete_id: int = 1) -> Athlete:
    athlete = Athlete(strava_athlete_id=strava_athlete_id)
    session.add(athlete)
    await session.flush()
    return athlete


async def _count(session: AsyncSession, model: type[object]) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def test_defaults_and_timezone(db_session: AsyncSession) -> None:
    athlete = await _athlete(db_session)
    await db_session.commit()
    await db_session.refresh(athlete)
    assert athlete.active is True
    assert athlete.created_at.tzinfo is not None


async def test_deleting_athlete_cascades(db_session: AsyncSession) -> None:
    athlete = await _athlete(db_session)
    db_session.add_all(
        [
            OAuthToken(
                athlete_id=athlete.id,
                access_token_enc=b"a",
                refresh_token_enc=b"r",
                expires_at=NOW,
                scope="read,activity:read_all",
            ),
            _activity(athlete.id, 100),
            _activity(athlete.id, 101),
            SyncRun(athlete_id=athlete.id, kind=SyncKind.BACKFILL, status=SyncStatus.RUNNING),
        ]
    )
    await db_session.commit()

    await db_session.execute(delete(Athlete).where(Athlete.id == athlete.id))
    await db_session.commit()

    for model in (Athlete, OAuthToken, Activity, SyncRun):
        assert await _count(db_session, model) == 0


@pytest.mark.parametrize(
    "duplicate",
    ["athlete", "activity", "webhook_event"],
)
async def test_unique_constraints(db_session: AsyncSession, duplicate: str) -> None:
    athlete = await _athlete(db_session)
    await db_session.commit()

    def rows() -> list[object]:
        if duplicate == "athlete":
            return [Athlete(strava_athlete_id=1)]
        if duplicate == "activity":
            return [_activity(athlete.id, 7), _activity(athlete.id, 7)]
        return [WebhookEvent(dedup_key="k", payload={}), WebhookEvent(dedup_key="k", payload={})]

    *first, last = rows()
    db_session.add_all(first)
    await db_session.flush()
    db_session.add(last)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.parametrize(
    "row",
    [
        lambda athlete_id: SyncRun(athlete_id=athlete_id, kind="bogus", status="running"),
        lambda athlete_id: SyncRun(athlete_id=athlete_id, kind="backfill", status="bogus"),
        lambda _: WebhookEvent(dedup_key="k", payload={}, status="bogus"),
    ],
    ids=["sync_kind", "sync_status", "webhook_status"],
)
async def test_check_constraints_reject_unknown_values(
    db_session: AsyncSession, row: object
) -> None:
    athlete = await _athlete(db_session)
    db_session.add(row(athlete.id))  # type: ignore[operator]
    with pytest.raises(IntegrityError):
        await db_session.flush()
