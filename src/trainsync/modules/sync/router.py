"""`GET /v1/sync/status`: how fresh and healthy syncing is."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from trainsync.core.deps import ClockDep, RedisDep, SessionmakerDep
from trainsync.core.errors import UNAUTHORIZED
from trainsync.integrations.strava.breaker import BreakerState
from trainsync.integrations.strava.breaker_status import overall_state, read_breakers
from trainsync.integrations.strava.budget import RateBudget
from trainsync.modules.activities.reads import ReadRepository
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.sync.models import SyncKind, SyncRun
from trainsync.modules.sync.status_repository import SyncStatusRepository

router = APIRouter(prefix="/v1/sync", tags=["sync"])

RUN_EXAMPLE: dict[str, Any] = {
    "id": 7,
    "status": "paused",
    "pages": 3,
    "upserted": 597,
    "error": None,
    "started_at": "2026-10-18T09:00:00Z",
    "updated_at": "2026-10-18T09:02:10Z",
    "finished_at": "2026-10-18T09:02:10Z",
}


class RunOut(BaseModel):
    id: int
    status: str
    pages: int
    upserted: int
    error: str | None
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None

    @classmethod
    def from_row(cls, run: SyncRun | None) -> "RunOut | None":
        if run is None:
            return None
        return cls(
            id=run.id,
            status=run.status,
            pages=run.pages,
            upserted=run.upserted,
            error=run.error,
            started_at=run.started_at,
            updated_at=run.updated_at,
            finished_at=run.finished_at,
        )


class AthleteSync(BaseModel):
    athlete_id: int
    strava_athlete_id: int
    backfill: RunOut | None
    incremental: RunOut | None


class WebhookStatusOut(BaseModel):
    last_received_at: datetime | None
    last_processed_at: datetime | None
    pending: int
    processing: int
    failed: int = Field(description="Failed, will be retried with backoff")
    dead_letters: int = Field(description="Failed 8 times; no longer retried")


class RateLimitOut(BaseModel):
    short_ratio: float = Field(description="Share of the 15-minute budget used")
    daily_ratio: float
    window_start: datetime
    blocked_until: datetime | None = Field(description="Set after a 429")


class BreakerProcess(BaseModel):
    process: str
    state: BreakerState
    retry_at: datetime | None
    changed_at: datetime


class CircuitOut(BaseModel):
    state: BreakerState = Field(description="Worst state across processes")
    processes: list[BreakerProcess]


class SyncStatusOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "athletes": [
                        {
                            "athlete_id": 1,
                            "strava_athlete_id": 134815,
                            "backfill": RUN_EXAMPLE,
                            "incremental": None,
                        }
                    ],
                    "webhooks": {
                        "last_received_at": "2026-10-18T09:20:00Z",
                        "last_processed_at": "2026-10-18T09:20:01Z",
                        "pending": 0,
                        "processing": 0,
                        "failed": 1,
                        "dead_letters": 0,
                    },
                    "rate_limit": {
                        "short_ratio": 0.82,
                        "daily_ratio": 0.31,
                        "window_start": "2026-10-18T09:00:00Z",
                        "blocked_until": None,
                    },
                    "circuit": {
                        "state": "open",
                        "processes": [
                            {
                                "process": "worker@host:41",
                                "state": "open",
                                "retry_at": "2026-10-18T09:21:30Z",
                                "changed_at": "2026-10-18T09:21:00Z",
                            }
                        ],
                    },
                    "last_synced_at": "2026-10-18T09:20:01Z",
                }
            ]
        }
    )

    athletes: list[AthleteSync]
    webhooks: WebhookStatusOut
    rate_limit: RateLimitOut | None = Field(description="Null until Strava has answered once")
    circuit: CircuitOut
    last_synced_at: datetime | None


@router.get(
    "/status",
    summary="Sync status",
    description=(
        "Latest backfill and incremental run per active athlete, webhook intake and retry "
        "counts, current Strava rate-limit usage, and the circuit breaker state of every "
        "process that talks to Strava."
    ),
    response_model=SyncStatusOut,
    responses=UNAUTHORIZED,
)
async def sync_status(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    redis: RedisDep,
    clock: ClockDep,
    athlete_id: Annotated[int | None, Query(description="Our athlete id")] = None,
) -> SyncStatusOut:
    async with sessionmaker() as session:
        reads = ReadRepository(session, principal.user_id)
        athlete_ids = await reads.active_athlete_ids(athlete_id)
        athletes = {a.id: a for a in await reads.athletes(athlete_ids)}
        status = SyncStatusRepository(session, principal.user_id)
        runs = await status.latest_runs(athlete_ids)
        webhooks = await status.webhook_summary()
        last_synced_at = await reads.last_synced_at(athlete_ids)

    now = clock()
    budget = await RateBudget(redis, clock).latest()
    breakers = await read_breakers(redis)
    return SyncStatusOut(
        athletes=[
            AthleteSync(
                athlete_id=aid,
                strava_athlete_id=athletes[aid].strava_athlete_id,
                backfill=RunOut.from_row(runs.get((aid, SyncKind.BACKFILL))),
                incremental=RunOut.from_row(runs.get((aid, SyncKind.INCREMENTAL))),
            )
            for aid in athlete_ids
        ],
        webhooks=WebhookStatusOut(
            last_received_at=webhooks.last_received_at,
            last_processed_at=webhooks.last_processed_at,
            pending=webhooks.pending,
            processing=webhooks.processing,
            failed=webhooks.failed,
            dead_letters=webhooks.dead_letters,
        ),
        rate_limit=None
        if budget is None
        else RateLimitOut(
            short_ratio=budget.short_ratio,
            daily_ratio=budget.daily_ratio,
            window_start=budget.window_start,
            blocked_until=budget.blocked_until,
        ),
        circuit=CircuitOut(
            state=overall_state(breakers, now),
            processes=[
                BreakerProcess(
                    process=b.process,
                    state=b.effective_state(now),
                    retry_at=b.retry_at,
                    changed_at=b.changed_at,
                )
                for b in breakers
            ],
        ),
        last_synced_at=last_synced_at,
    )
