"""Client for trainsync's own API (`/v1`), used by the bot and the assistant.

The bot never touches the database: it reads and writes through the same HTTP API as every other
client, with its service key, and parses responses with the API's own response models. Inside
`using_user()` (the chat's linked user, ADR 0036) every call carries `X-Acting-User`. Writes are
idempotent `PUT`s keyed by client ids the bot derives from the Telegram update (ADR 0017), so a
retried request or a redelivered update stores one row.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel, SecretStr

from trainsync.modules.activities.router import ActivityDetail, ActivityPage
from trainsync.modules.chat.router import ChatOwner, LinkIn
from trainsync.modules.checkin.router import CheckinIn, CheckinOut, CheckinSummary
from trainsync.modules.coach.mode import CURRENT_USER
from trainsync.modules.nutrition.schemas import DaySummary, FoodList, FoodLookup, LogIn, LogOut
from trainsync.modules.stats.periods import Period
from trainsync.modules.stats.totals import ActivitySummary, StatsSummary, WeeklyStats
from trainsync.modules.sync.router import SyncStatusOut
from trainsync.modules.training.routes.exercises import ExerciseList
from trainsync.modules.training.routes.next_day import NextDay
from trainsync.modules.training.routes.planning import PlatesOut
from trainsync.modules.training.routes.progress import BodyMetricIn, BodyMetricOut
from trainsync.modules.training.schemas import SetOut
from trainsync.modules.training.workout_schemas import SetIn, WorkoutDetail, WorkoutPage
from trainsync.modules.users.schemas import SettingsOut, SettingsPatch

ACTING_USER_HEADER = "X-Acting-User"
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404


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

    async def summary(
        self, start: date, end: date, sport_type: str | None = None
    ) -> ActivitySummary:
        params = _params(start=start, end=end, sport_type=sport_type)
        return await self._get("/v1/stats/summary", params, ActivitySummary)

    async def progress(self, period: Period) -> StatsSummary:
        """The progress summary of the acting user (P8.11)."""
        return await self._get("/v1/stats/summary", {"period": period.value}, StatsSummary)

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

    # ---------------------------------------------------------------- chats and settings (P8.4)

    async def chat_owner(self, chat_id: int) -> ChatOwner | None:
        """The linked user of a chat, or None when the chat is not linked."""
        try:
            return await self._get(f"/v1/telegram/chats/{chat_id}", {}, ChatOwner)
        except ReadApiError as exc:
            if exc.status == HTTP_NOT_FOUND:
                return None
            raise

    async def link_chat(self, chat_id: int, code: str) -> ChatOwner | None:
        """None when the code is unknown, used or expired."""
        body = LinkIn(code=code).model_dump(mode="json")
        try:
            return await self._send("POST", f"/v1/telegram/chats/{chat_id}/link", body, ChatOwner)
        except ReadApiError as exc:
            if exc.status == HTTP_BAD_REQUEST:
                return None
            raise

    async def unlink_chat(self, chat_id: int) -> None:
        await self._request("DELETE", f"/v1/telegram/chats/{chat_id}")

    async def patch_settings(self, body: SettingsPatch) -> SettingsOut:
        changes = body.model_dump(mode="json", exclude_unset=True)
        return await self._send("PATCH", "/v1/me/settings", changes, SettingsOut)

    async def _get[M: BaseModel](self, path: str, params: dict[str, Any], model: type[M]) -> M:
        response = await self._request("GET", path, params=params)
        return model.model_validate(response.json())

    async def _send[M: BaseModel](
        self, method: str, path: str, body: dict[str, Any], model: type[M]
    ) -> M:
        response = await self._request(method, path, body=body)
        return model.model_validate(response.json())

    def _headers(self) -> dict[str, str]:
        headers = {"X-API-Key": self._api_key.get_secret_value()}
        user = CURRENT_USER.get()
        if user is not None:
            headers[ACTING_USER_HEADER] = str(user)
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        try:
            response = await self._http.request(
                method,
                f"{self._base_url}{path}",
                params=params,
                json=body,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise ReadApiError(f"{method} {path}: {type(exc).__name__}") from None
        if response.status_code not in (200, 201, 204):
            raise ReadApiError(
                f"{method} {path}: HTTP {response.status_code}", response.status_code
            )
        return response


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
