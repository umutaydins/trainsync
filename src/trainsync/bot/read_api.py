"""Client for trainsync's own API (`/v1`), used by the bot and the assistant.

The bot never touches the database: it reads and writes through the same HTTP API as every other
client, with an API key, and parses responses with the API's own response models. Writes are
idempotent `PUT`s keyed by client ids the bot derives from the Telegram update (ADR 0017), so a
retried request or a redelivered update stores one row.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel, SecretStr

from trainsync.api.activities import ActivityDetail, ActivityPage
from trainsync.api.chats import ChatSettingsIn, ChatSettingsOut
from trainsync.api.checkins import CheckinIn, CheckinOut, CheckinSummary
from trainsync.api.nutrition import DaySummary, FoodList, FoodLookup, LogIn, LogOut
from trainsync.api.stats import StatsSummary, WeeklyStats
from trainsync.api.sync_status import SyncStatusOut
from trainsync.api.training.common import SetOut
from trainsync.api.training.exercises import ExerciseList
from trainsync.api.training.next_day import NextDay
from trainsync.api.training.planning import PlatesOut
from trainsync.api.training.progress import BodyMetricIn, BodyMetricOut
from trainsync.api.training.workouts import SetIn, WorkoutDetail, WorkoutPage


class ReadApiError(Exception):
    """The API answered with an error or could not be reached."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ReadApi:
    """Read and write client (the name predates writes, P6.8)."""

    def __init__(self, http: httpx.AsyncClient, base_url: str, api_key: SecretStr) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    # ---------------------------------------------------------------- activities and stats

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

    # ---------------------------------------------------------------- training (P6.8)

    async def exercises(self, q: str) -> ExerciseList:
        return await self._get("/v1/training/exercises", {"q": q}, ExerciseList)

    async def next_day(self) -> NextDay | None:
        """The active program's next day, or None when no program is active."""
        try:
            return await self._get("/v1/training/programs/active/next-day", {}, NextDay)
        except ReadApiError as exc:
            if exc.status == 404:
                return None
            raise

    async def workouts(self, limit: int = 5) -> WorkoutPage:
        return await self._get("/v1/training/workouts", {"limit": limit}, WorkoutPage)

    async def workout(self, workout_id: int) -> WorkoutDetail:
        return await self._get(f"/v1/training/workouts/{workout_id}", {}, WorkoutDetail)

    async def start_workout(
        self, client_id: uuid.UUID, started_at: datetime, program_day_id: int | None = None
    ) -> WorkoutDetail:
        """Idempotent by `client_id`: a redelivered update starts nothing new (ADR 0017)."""
        body: dict[str, Any] = {"started_at": started_at.isoformat()}
        if program_day_id is not None:
            body["program_day_id"] = program_day_id
        path = f"/v1/training/workouts/{client_id}"
        return await self._send("PUT", path, body, WorkoutDetail)

    async def put_set(self, workout_id: int, client_id: uuid.UUID, body: SetIn) -> SetOut:
        path = f"/v1/training/workouts/{workout_id}/sets/{client_id}"
        return await self._send("PUT", path, body.model_dump(mode="json"), SetOut)

    async def finish_workout(self, workout_id: int, ended_at: datetime) -> WorkoutDetail:
        path = f"/v1/training/workouts/{workout_id}/finish"
        return await self._send("POST", path, {"ended_at": ended_at.isoformat()}, WorkoutDetail)

    async def plates(self, target_kg: Decimal) -> PlatesOut:
        return await self._get("/v1/training/plates", {"target": str(target_kg)}, PlatesOut)

    async def put_body_metric(self, day: date, weight_kg: Decimal) -> BodyMetricOut:
        body = BodyMetricIn(weight_kg=weight_kg).model_dump(mode="json")
        path = f"/v1/training/body-metrics/{day.isoformat()}"
        return await self._send("PUT", path, body, BodyMetricOut)

    # ---------------------------------------------------------------- nutrition (P6.8)

    async def foods(self, q: str, limit: int = 10) -> FoodList:
        return await self._get("/v1/nutrition/foods", {"q": q, "limit": limit}, FoodList)

    async def put_food_log(self, client_id: uuid.UUID, body: LogIn) -> LogOut:
        path = f"/v1/nutrition/log/{client_id}"
        return await self._send("PUT", path, body.model_dump(mode="json"), LogOut)

    async def food_lookup(self, q: str, limit: int = 5) -> FoodLookup:
        return await self._get("/v1/nutrition/foods/lookup", {"q": q, "limit": limit}, FoodLookup)

    async def nutrition_summary(self, day: date) -> DaySummary:
        return await self._get("/v1/nutrition/summary", {"date": day.isoformat()}, DaySummary)

    # ---------------------------------------------------------------- check-ins (P6.9)

    async def put_checkin(self, day: date, body: CheckinIn) -> CheckinOut:
        path = f"/v1/checkins/{day.isoformat()}"
        return await self._send("PUT", path, body.model_dump(mode="json"), CheckinOut)

    async def checkin_summary(self, today: date) -> CheckinSummary:
        params = {"to": today.isoformat()}
        return await self._get("/v1/checkins/summary", params, CheckinSummary)

    # ---------------------------------------------------------------- transport

    # ---------------------------------------------------------------- chat settings (P6.12)

    async def chat_settings(self, chat_id: int) -> ChatSettingsOut:
        return await self._get(f"/v1/chats/{chat_id}/settings", {}, ChatSettingsOut)

    async def put_chat_settings(self, chat_id: int, body: ChatSettingsIn) -> ChatSettingsOut:
        path = f"/v1/chats/{chat_id}/settings"
        body_json = body.model_dump(mode="json", exclude_none=True)
        return await self._send("PUT", path, body_json, ChatSettingsOut)

    async def _get[M: BaseModel](self, path: str, params: dict[str, Any], model: type[M]) -> M:
        return await self._request("GET", path, model, params=params)

    async def _send[M: BaseModel](
        self, method: str, path: str, body: dict[str, Any], model: type[M]
    ) -> M:
        return await self._request(method, path, model, body=body)

    async def _request[M: BaseModel](
        self,
        method: str,
        path: str,
        model: type[M],
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> M:
        try:
            response = await self._http.request(
                method,
                f"{self._base_url}{path}",
                params=params,
                json=body,
                headers={"X-API-Key": self._api_key.get_secret_value()},
            )
        except httpx.HTTPError as exc:
            raise ReadApiError(f"{method} {path}: {type(exc).__name__}") from None
        if response.status_code not in (200, 201):
            raise ReadApiError(
                f"{method} {path}: HTTP {response.status_code}", response.status_code
            )
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
