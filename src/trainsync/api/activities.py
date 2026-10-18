"""`GET /v1/activities`: stored activities, newest first, keyset-paginated (ADR 0009).

`GET /v1/activities/{strava_activity_id}`: one stored activity.
"""

import base64
import binascii
import json
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field

from trainsync.api.deps import SessionmakerDep, require_api_key
from trainsync.api.errors import UNAUTHORIZED, error
from trainsync.db.models import Activity
from trainsync.db.repositories.reads import ActivityFilter, Keyset, ReadRepository

router = APIRouter(prefix="/v1", tags=["activities"], dependencies=[Depends(require_api_key)])

ACTIVITY_EXAMPLE: dict[str, Any] = {
    "id": 10000000123,
    "athlete_id": 1,
    "name": "Morning Run",
    "sport_type": "Run",
    "start_date": "2026-10-01T06:30:00Z",
    "distance_m": 10012.5,
    "moving_time_s": 3000,
    "elapsed_time_s": 3100,
    "elevation_gain_m": 42.0,
    "average_heartrate": 151.2,
    "synced_at": "2026-10-01T07:02:11Z",
}


class ActivityOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [ACTIVITY_EXAMPLE]})

    id: int = Field(description="Strava activity id")
    athlete_id: int
    name: str
    sport_type: str
    start_date: datetime
    distance_m: float
    moving_time_s: int
    elapsed_time_s: int
    elevation_gain_m: float
    average_heartrate: float | None
    synced_at: datetime
    raw: dict[str, Any] | None = Field(
        default=None, description="Strava's JSON, only with `include=raw`"
    )

    @classmethod
    def from_row(cls, row: Activity, *, include_raw: bool) -> "ActivityOut":
        return cls(
            id=row.strava_activity_id,
            athlete_id=row.athlete_id,
            name=row.name,
            sport_type=row.sport_type,
            start_date=row.start_date,
            distance_m=row.distance_m,
            moving_time_s=row.moving_time_s,
            elapsed_time_s=row.elapsed_time_s,
            elevation_gain_m=row.elevation_gain_m,
            average_heartrate=row.average_heartrate,
            synced_at=row.synced_at,
            raw=row.raw if include_raw else None,
        )


class ActivityPage(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [ACTIVITY_EXAMPLE],
                    "next_cursor": "eyJzdGFydF9kYXRlIjogIjIwMjYtMTAtMDFUMDY6MzA6MDBaIiwgImlkIjogNDJ9",  # noqa: E501
                    "last_synced_at": "2026-10-18T09:30:02Z",
                }
            ]
        }
    )

    items: list[ActivityOut]
    next_cursor: str | None = Field(
        description="Pass as `cursor` for the next page; null at the end"
    )
    last_synced_at: datetime | None = Field(
        description="When data was last written by any sync path; tells how fresh this is"
    )


class ActivityDetail(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"activity": ACTIVITY_EXAMPLE, "last_synced_at": "2026-10-18T09:30:02Z"}]
        }
    )

    activity: ActivityOut
    last_synced_at: datetime | None = Field(
        description="When data was last written by any sync path; tells how fresh this is"
    )


def encode_cursor(keyset: Keyset) -> str:
    raw = json.dumps({"start_date": keyset.start_date.isoformat(), "id": keyset.id})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> Keyset:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        start_date = datetime.fromisoformat(data["start_date"])
        row_id = data["id"]
        if not isinstance(row_id, int) or start_date.tzinfo is None:
            raise ValueError("bad cursor fields")
    except (ValueError, KeyError, TypeError, binascii.Error, UnicodeDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from exc
    return Keyset(start_date, row_id)


def as_utc(value: datetime | None) -> datetime | None:
    """Naive datetimes (e.g. `from=2026-10-01`) are taken as UTC."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


@router.get(
    "/activities",
    summary="List activities",
    description=(
        "Stored activities of all active athletes (or one, with `athlete_id`), newest first. "
        "Soft-deleted activities are excluded. Pages are keyset-based: pass `next_cursor` back as "
        "`cursor`. Rows inserted while paging never shift or repeat a page."
    ),
    response_model=ActivityPage,
    response_model_exclude_none=False,
    responses={**UNAUTHORIZED, 400: error("Invalid cursor", "invalid cursor")},
)
async def list_activities(
    sessionmaker: SessionmakerDep,
    start_from: Annotated[
        datetime | None,
        Query(
            alias="from",
            description="Start date ≥ this (UTC if no offset)",
            examples=["2026-10-01"],
        ),
    ] = None,
    start_to: Annotated[
        datetime | None,
        Query(
            alias="to", description="Start date < this (UTC if no offset)", examples=["2026-11-01"]
        ),
    ] = None,
    sport_type: Annotated[str | None, Query(examples=["Run"])] = None,
    athlete_id: Annotated[int | None, Query(description="Our athlete id")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(description="`next_cursor` of the previous page")] = None,
    include: Annotated[Literal["raw"] | None, Query(description="`raw` adds Strava's JSON")] = None,
) -> ActivityPage:
    after = decode_cursor(cursor) if cursor else None
    async with sessionmaker() as session:
        reads = ReadRepository(session)
        athlete_ids = await reads.active_athlete_ids(athlete_id)
        activity_filter = ActivityFilter(
            athlete_ids, as_utc(start_from), as_utc(start_to), sport_type
        )
        rows, next_keyset = await reads.activity_page(activity_filter, after, limit)
        last_synced_at = await reads.last_synced_at(athlete_ids)
    return ActivityPage(
        items=[ActivityOut.from_row(r, include_raw=include == "raw") for r in rows],
        next_cursor=encode_cursor(next_keyset) if next_keyset else None,
        last_synced_at=last_synced_at,
    )


@router.get(
    "/activities/{strava_activity_id}",
    summary="Get one activity",
    description=(
        "One stored activity of an active athlete, by its Strava id. Unknown and soft-deleted "
        "activities are 404."
    ),
    response_model=ActivityDetail,
    response_model_exclude_none=False,
    responses={**UNAUTHORIZED, 404: error("Unknown or deleted activity", "activity not found")},
)
async def get_activity(
    sessionmaker: SessionmakerDep,
    strava_activity_id: Annotated[
        int, Path(description="Strava activity id", examples=[10000000123])
    ],
    include: Annotated[Literal["raw"] | None, Query(description="`raw` adds Strava's JSON")] = None,
) -> ActivityDetail:
    async with sessionmaker() as session:
        reads = ReadRepository(session)
        row = await reads.activity(strava_activity_id, await reads.active_athlete_ids())
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "activity not found")
        last_synced_at = await reads.last_synced_at([row.athlete_id])
    return ActivityDetail(
        activity=ActivityOut.from_row(row, include_raw=include == "raw"),
        last_synced_at=last_synced_at,
    )
