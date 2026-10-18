"""Client for trainsync's own read API (`/v1`), used by the bot and the assistant.

The bot never touches the database: it reads through the same HTTP API as every other client,
with an API key, and parses responses with the API's own response models.
"""

from datetime import date, datetime
from typing import Any

import httpx
from pydantic import BaseModel, SecretStr

from trainsync.api.activities import ActivityDetail, ActivityPage
from trainsync.api.stats import StatsSummary, WeeklyStats
from trainsync.api.sync_status import SyncStatusOut


class ReadApiError(Exception):
    """The read API answered with an error or could not be reached."""


class ReadApi:
    def __init__(self, http: httpx.AsyncClient, base_url: str, api_key: SecretStr) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def summary(self, start: date, end: date, sport_type: str | None = None) -> StatsSummary:
        params = _params(start=start, end=end, sport_type=sport_type)
        return await self._get("/v1/stats/summary", params, StatsSummary)

    async def weekly(self, start: date, end: date, sport_type: str | None = None) -> WeeklyStats:
        params = _params(start=start, end=end, sport_type=sport_type)
        return await self._get("/v1/stats/weekly", params, WeeklyStats)

    async def activities(
        self,
        *,
        start: date | datetime | None = None,
        end: date | datetime | None = None,
        sport_type: str | None = None,
        limit: int = 1,
    ) -> ActivityPage:
        params = _params(start=start, end=end, sport_type=sport_type)
        params["limit"] = limit
        return await self._get("/v1/activities", params, ActivityPage)

    async def activity(self, strava_activity_id: int) -> ActivityDetail:
        return await self._get(f"/v1/activities/{strava_activity_id}", {}, ActivityDetail)

    async def sync_status(self) -> SyncStatusOut:
        return await self._get("/v1/sync/status", {}, SyncStatusOut)

    async def _get[M: BaseModel](self, path: str, params: dict[str, Any], model: type[M]) -> M:
        try:
            response = await self._http.get(
                f"{self._base_url}{path}",
                params=params,
                headers={"X-API-Key": self._api_key.get_secret_value()},
            )
        except httpx.HTTPError as exc:
            raise ReadApiError(f"{path}: {type(exc).__name__}") from None
        if response.status_code != 200:
            raise ReadApiError(f"{path}: HTTP {response.status_code}")
        return model.model_validate(response.json())


def _params(
    *,
    start: date | datetime | None,
    end: date | datetime | None,
    sport_type: str | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if start is not None:
        params["from"] = start.isoformat()
    if end is not None:
        params["to"] = end.isoformat()
    if sport_type:
        params["sport_type"] = sport_type
    return params
