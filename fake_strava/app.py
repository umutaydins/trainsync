"""fake_strava HTTP app.

Run: `uv run uvicorn fake_strava.app:create_app --factory --port 8001`.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

from fake_strava.clock import Clock, SystemClock
from fake_strava.config import FakeStravaConfig
from fake_strava.state import FakeStravaState, OAuthError
from fake_strava.webhooks import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_TIMEOUT_S,
    DeliveryReport,
    FireRequest,
    WebhookEvent,
    fire,
)

API_PREFIX = "/api/v3"
CONTROL_PREFIX = "/_control"
MAX_PER_PAGE = 200

_ERROR_MESSAGES = {500: "Internal Server Error", 502: "Bad Gateway", 503: "Service Unavailable"}


class StravaHTTPError(Exception):
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        super().__init__(status)
        self.status = status
        self.body = body


def _error(message: str, resource: str, field: str, code: str) -> dict[str, Any]:
    return {"message": message, "errors": [{"resource": resource, "field": field, "code": code}]}


def get_state(request: Request) -> FakeStravaState:
    state: FakeStravaState = request.app.state.fake
    return state


StateDep = Annotated[FakeStravaState, Depends(get_state)]


def current_athlete(state: StateDep, authorization: Annotated[str | None, Header()] = None) -> int:
    scheme, _, token = (authorization or "").partition(" ")
    athlete_id = state.authenticate(token.strip()) if scheme.lower() == "bearer" else None
    if athlete_id is None:
        raise StravaHTTPError(
            401, _error("Authorization Error", "Athlete", "access_token", "invalid")
        )
    return athlete_id


AthleteDep = Annotated[int, Depends(current_athlete)]


class ActivityChangeRequest(BaseModel):
    action: Literal["create", "update", "delete"]
    id: int | None = None
    athlete_id: int | None = None
    fields: dict[str, Any] = Field(default_factory=dict)


class ExpireTokensRequest(BaseModel):
    athlete_id: int | None = None


class ScenarioRequest(BaseModel):
    target_url: str
    athlete_id: int | None = None
    subscription_id: int | None = None
    timeout_s: float = Field(default=DEFAULT_TIMEOUT_S, gt=0)
    max_attempts: int = Field(default=DEFAULT_MAX_ATTEMPTS, ge=1, le=10)


class LifecycleRequest(ScenarioRequest):
    activity_id: int | None = None
    title: str = "Renamed by the athlete"
    delete: bool = True
    out_of_order: bool = False


class ScenarioResponse(BaseModel):
    activity_id: int | None = None
    events: list[WebhookEvent]
    report: DeliveryReport


def create_app(
    config: FakeStravaConfig | None = None,
    clock: Clock | None = None,
    webhook_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """`webhook_transport` lets tests deliver webhooks in-process (e.g. `httpx.ASGITransport`)."""
    app = FastAPI(title="fake_strava", docs_url="/_docs", openapi_url="/_openapi.json")
    app.state.fake = FakeStravaState(config or FakeStravaConfig(), clock or SystemClock())
    app.state.webhook_transport = webhook_transport

    @app.exception_handler(StravaHTTPError)
    async def _strava_error(_: Request, exc: StravaHTTPError) -> Response:
        return JSONResponse(exc.body, status_code=exc.status)

    app.add_middleware(BaseHTTPMiddleware, dispatch=_api_middleware)
    _add_oauth_routes(app)
    _add_api_routes(app)
    _add_control_routes(app)
    _add_webhook_routes(app)
    return app


async def _api_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    state: FakeStravaState = request.app.state.fake
    path = request.url.path
    if path.startswith(CONTROL_PREFIX) or path.startswith("/_docs") or path == "/_openapi.json":
        return await call_next(request)
    endpoint = f"{request.method} {_route_template(request)}"
    if not path.startswith(API_PREFIX):
        response = await call_next(request)
        state.record(endpoint, response.status_code)
        return response

    if state.config.latency_ms > 0:
        await asyncio.sleep(state.config.latency_ms / 1000)
    decision = state.consume_rate_limit()
    if not decision.allowed:
        response = JSONResponse(
            _error("Rate Limit Exceeded", "Application", "rate limit", "exceeded"),
            status_code=429,
        )
    elif (status := state.injected_error()) is not None:
        response = JSONResponse({"message": _ERROR_MESSAGES[status]}, status_code=status)
    else:
        response = await call_next(request)
    response.headers.update(decision.headers)
    state.record(endpoint, response.status_code)
    return response


def _route_template(request: Request) -> str:
    for route in request.app.router.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            path: str = getattr(route, "path", request.url.path)
            return path
    return request.url.path


def _add_oauth_routes(app: FastAPI) -> None:
    @app.get("/oauth/authorize")
    async def authorize(
        state: StateDep,
        redirect_uri: str,
        client_id: str | None = None,
        response_type: str = "code",
        scope: str = "read",
        state_param: Annotated[str | None, Query(alias="state")] = None,
        approval_prompt: str | None = None,
        athlete_id: int | None = None,
    ) -> Response:
        """Approves immediately as the default (or given) athlete."""
        if response_type != "code":
            raise StravaHTTPError(
                400, _error("Bad Request", "Application", "response_type", "invalid")
            )
        try:
            code = state.issue_code(athlete_id or state.default_athlete_id, scope)
        except OAuthError as exc:
            raise StravaHTTPError(
                400, _error("Bad Request", "Athlete", exc.field_name, "invalid")
            ) from exc
        params = {"code": code, "scope": scope}
        if state_param is not None:
            params = {"state": state_param, **params}
        return RedirectResponse(_with_query(redirect_uri, params), status_code=302)

    @app.post("/oauth/token")
    async def token(request: Request, state: StateDep) -> dict[str, Any]:
        form = await _read_form(request)
        try:
            state.check_client(form.get("client_id"), form.get("client_secret"))
            grant_type = form.get("grant_type")
            if grant_type == "authorization_code":
                grant = state.exchange_code(form.get("code", ""))
                return grant.to_json(with_athlete=True, ttl_s=state.config.token_ttl_s)
            if grant_type == "refresh_token":
                grant = state.refresh(form.get("refresh_token", ""))
                return grant.to_json(with_athlete=False, ttl_s=state.config.token_ttl_s)
            raise OAuthError("grant_type")
        except OAuthError as exc:
            raise StravaHTTPError(
                400, _error("Bad Request", "AuthorizationCode", exc.field_name, "invalid")
            ) from exc

    @app.post("/oauth/deauthorize")
    async def deauthorize(request: Request, state: StateDep) -> dict[str, Any]:
        """Like Strava: revokes every token of the athlete the access token belongs to."""
        form = await _read_form(request)
        athlete_id = state.authenticate(form.get("access_token", ""))
        if athlete_id is None:
            raise StravaHTTPError(
                401, _error("Authorization Error", "Athlete", "access_token", "invalid")
            )
        state.revoke(athlete_id)
        state.deauthorized.append(athlete_id)
        return {"access_token": form.get("access_token", "")}


def _add_api_routes(app: FastAPI) -> None:
    @app.get(f"{API_PREFIX}/athlete")
    async def athlete(state: StateDep, athlete_id: AthleteDep) -> dict[str, Any]:
        return state.athletes[athlete_id].to_json()

    @app.get(f"{API_PREFIX}/athlete/activities")
    async def list_activities(
        state: StateDep,
        athlete_id: AthleteDep,
        before: int | None = None,
        after: int | None = None,
        page: Annotated[int, Query(ge=1)] = 1,
        per_page: Annotated[int, Query(ge=1)] = 30,
    ) -> list[dict[str, Any]]:
        items = state.list_activities(
            athlete_id,
            before=before,
            after=after,
            page=page,
            per_page=min(per_page, MAX_PER_PAGE),
        )
        return [a.to_json() for a in items]

    @app.get(f"{API_PREFIX}/activities/{{activity_id}}")
    async def get_activity(
        state: StateDep, athlete_id: AthleteDep, activity_id: int
    ) -> dict[str, Any]:
        activity = state.get_activity(athlete_id, activity_id)
        if activity is None:
            raise StravaHTTPError(404, _error("Record Not Found", "Activity", "id", "not found"))
        return activity.to_json()


def _add_control_routes(app: FastAPI) -> None:
    @app.post(f"{CONTROL_PREFIX}/config")
    async def set_config(request: Request, state: StateDep) -> dict[str, Any]:
        changes = await request.json()
        if not isinstance(changes, dict):
            raise StravaHTTPError(422, {"message": "config must be a JSON object"})
        try:
            return state.update_config(changes).model_dump()
        except ValueError as exc:
            raise StravaHTTPError(422, {"message": str(exc)}) from exc

    @app.get(f"{CONTROL_PREFIX}/config")
    async def get_config(state: StateDep) -> dict[str, Any]:
        return state.config.model_dump()

    @app.post(f"{CONTROL_PREFIX}/reset")
    async def reset(state: StateDep) -> dict[str, Any]:
        state.reset()
        return {"status": "reset", "activities": len(state.activities)}

    @app.get(f"{CONTROL_PREFIX}/stats")
    async def stats(state: StateDep) -> dict[str, Any]:
        return state.stats_json()

    @app.post(f"{CONTROL_PREFIX}/activities")
    async def change_activity(body: ActivityChangeRequest, state: StateDep) -> dict[str, Any]:
        try:
            activity = state.apply_change(
                body.action, athlete_id=body.athlete_id, activity_id=body.id, fields=body.fields
            )
        except KeyError as exc:
            raise StravaHTTPError(404, {"message": f"unknown {exc.args[0]}"}) from exc
        except ValueError as exc:
            raise StravaHTTPError(422, {"message": str(exc)}) from exc
        change = state.changes[-1]
        return {
            "action": change.action,
            "id": change.activity_id,
            "athlete_id": change.athlete_id,
            "activity": None if activity is None else activity.to_json(),
        }

    @app.post(f"{CONTROL_PREFIX}/expire-tokens")
    async def expire_tokens(
        state: StateDep, body: ExpireTokensRequest | None = None
    ) -> dict[str, int]:
        return {"expired": state.expire_tokens(body.athlete_id if body else None)}


def _add_webhook_routes(app: FastAPI) -> None:
    @app.post(f"{CONTROL_PREFIX}/webhooks/fire")
    async def fire_webhooks(body: FireRequest, request: Request) -> DeliveryReport:
        return await _fire(request, body)

    @app.post(f"{CONTROL_PREFIX}/scenario/activity-lifecycle")
    async def activity_lifecycle(
        body: LifecycleRequest, request: Request, state: StateDep
    ) -> ScenarioResponse:
        """Create → rename → (delete) one activity in the fake's state, then fire the matching
        events (shuffled when `out_of_order`)."""
        try:
            created = state.apply_change(
                "create", athlete_id=body.athlete_id, activity_id=body.activity_id, fields={}
            )
        except KeyError as exc:
            raise StravaHTTPError(404, {"message": f"unknown {exc.args[0]}"}) from exc
        except ValueError as exc:
            raise StravaHTTPError(422, {"message": str(exc)}) from exc
        if created is None:
            raise RuntimeError("create returned no activity")
        state.apply_change(
            "update", athlete_id=None, activity_id=created.id, fields={"name": body.title}
        )
        steps: list[tuple[Literal["create", "update", "delete"], dict[str, Any]]] = [
            ("create", {}),
            ("update", {"title": body.title}),
        ]
        if body.delete:
            state.apply_change("delete", athlete_id=None, activity_id=created.id, fields={})
            steps.append(("delete", {}))
        base_time = int(state.clock.now().timestamp())
        events = [
            WebhookEvent(
                object_type="activity",
                object_id=created.id,
                aspect_type=aspect,
                updates=updates,
                owner_id=created.athlete_id,
                subscription_id=_subscription(state, body),
                event_time=base_time + offset,
            )
            for offset, (aspect, updates) in enumerate(steps)
        ]
        mode: Literal["single", "out_of_order"] = "out_of_order" if body.out_of_order else "single"
        report = await _fire(request, _fire_request(body, events, mode))
        return ScenarioResponse(activity_id=created.id, events=events, report=report)

    @app.post(f"{CONTROL_PREFIX}/scenario/deauthorize")
    async def deauthorize(
        body: ScenarioRequest, request: Request, state: StateDep
    ) -> ScenarioResponse:
        """The athlete revokes access in Strava settings: tokens die, a deauth event is fired."""
        athlete_id = body.athlete_id or state.default_athlete_id
        if athlete_id not in state.athletes:
            raise StravaHTTPError(404, {"message": "unknown athlete"})
        state.revoke(athlete_id)
        event = WebhookEvent(
            object_type="athlete",
            object_id=athlete_id,
            aspect_type="update",
            updates={"authorized": "false"},
            owner_id=athlete_id,
            subscription_id=_subscription(state, body),
            event_time=int(state.clock.now().timestamp()),
        )
        report = await _fire(request, _fire_request(body, [event], "single"))
        return ScenarioResponse(events=[event], report=report)


def _subscription(state: FakeStravaState, body: ScenarioRequest) -> int:
    if body.subscription_id is not None:
        return body.subscription_id
    return state.config.webhook_subscription_id


def _fire_request(
    body: ScenarioRequest,
    events: list[WebhookEvent],
    mode: Literal["single", "duplicate", "out_of_order"],
) -> FireRequest:
    return FireRequest(
        target_url=body.target_url,
        events=events,
        mode=mode,
        timeout_s=body.timeout_s,
        max_attempts=body.max_attempts,
    )


async def _fire(request: Request, body: FireRequest) -> DeliveryReport:
    state: FakeStravaState = request.app.state.fake
    transport: httpx.AsyncBaseTransport | None = request.app.state.webhook_transport
    async with httpx.AsyncClient(transport=transport) as http:
        return await fire(body, http, state.webhook_rng)


async def _read_form(request: Request) -> dict[str, str]:
    """Strava accepts form, JSON or query parameters; python-multipart is not needed for this."""
    fields = dict(request.query_params)
    body = await request.body()
    if body:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            data = json.loads(body)
            if isinstance(data, dict):
                fields.update({k: str(v) for k, v in data.items()})
        else:
            fields.update(parse_qsl(body.decode(), keep_blank_values=True))
    return fields


def _with_query(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = "&".join(q for q in (parts.query, urlencode(params)) if q)
    return urlunsplit(parts._replace(query=query))
