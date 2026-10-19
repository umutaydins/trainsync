"""OAuth connect: redirect to Strava, handle the callback, store tokens, enqueue a backfill.

The signed `state` names the user who started the connect (ADR 0037): the callback is a plain
browser redirect from Strava, so the state is the only proof of who it is for.
"""

import json
from datetime import datetime
from typing import Annotated
from urllib.parse import urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from trainsync.core.deps import CipherDep, ClockDep, JobQueueDep, SessionmakerDep, SettingsDep
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.core.logging import get_logger
from trainsync.core.settings import Settings
from trainsync.core.state import InvalidStateError, sign_state, verify_state
from trainsync.integrations.strava.errors import StravaAuthError
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.strava.dependencies import StravaDep
from trainsync.modules.strava.repository import AthleteRepository, AthleteTakenError
from trainsync.modules.strava.token_repository import TokenRepository

router = APIRouter(prefix="/auth/strava", tags=["auth"])
me_router = APIRouter(prefix="/v1/me/strava", tags=["me"], responses=UNAUTHORIZED)
log = get_logger(__name__)

REQUESTED_SCOPE = "read,activity:read_all"
REQUIRED_SCOPE = "activity:read_all"


class ConnectedResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"athlete_id": 1, "strava_athlete_id": 134815, "backfill": "queued"}]
        }
    )

    athlete_id: int
    strava_athlete_id: int
    backfill: str


class StravaConnection(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "connected": True,
                    "athlete_id": 1,
                    "strava_athlete_id": 134815,
                    "connected_at": "2026-10-19T08:00:00Z",
                }
            ]
        }
    )

    connected: bool
    athlete_id: int | None = None
    strava_athlete_id: int | None = None
    connected_at: datetime | None = None


class AuthorizeUrl(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"url": "https://www.strava.com/oauth/authorize?client_id=1234&…"}]
        }
    )

    url: str = Field(description="Send the browser here; valid for a few minutes")


def state_data(user_id: int, return_to: str) -> str:
    return json.dumps({"u": user_id, "r": return_to}, separators=(",", ":"))


def parse_state_data(data: str) -> tuple[int, str]:
    try:
        parsed = json.loads(data)
        return int(parsed["u"]), str(parsed.get("r") or "")
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidStateError("state carries no user") from exc


def authorize_url(settings: Settings, now: datetime, user_id: int, return_to: str) -> str:
    query = urlencode(
        {
            "client_id": settings.strava_client_id,
            "redirect_uri": settings.strava_redirect_uri,
            "response_type": "code",
            "approval_prompt": "auto",
            "scope": REQUESTED_SCOPE,
            "state": sign_state(
                now, settings.state_signing_key, data=state_data(user_id, return_to)
            ),
        }
    )
    return f"{settings.strava_oauth_public_base_url}/authorize?{query}"


@router.get(
    "/login",
    summary="Start the Strava OAuth flow",
    description=(
        "Redirects the browser to Strava's authorize page with a signed, expiring `state`. "
        "An optional `return_to` that exactly matches `OAUTH_RETURN_TO_ALLOWLIST` is signed into "
        "the state; after the callback the browser is sent there. Any other value is ignored."
    ),
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
    responses=UNAUTHORIZED,
)
async def login(
    principal: CurrentUser,
    settings: SettingsDep,
    clock: ClockDep,
    return_to: Annotated[
        str | None,
        Query(
            description="Where to send the browser after connecting (allowlisted URLs only)",
            examples=["http://localhost:3000/sync"],
        ),
    ] = None,
) -> RedirectResponse:
    allowed = allowed_return_to(return_to, settings)
    if return_to and not allowed:
        log.warning("oauth_return_to_ignored")
    url = authorize_url(settings, clock(), principal.user_id, allowed)
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@router.get(
    "/callback",
    summary="Strava OAuth callback",
    description=(
        "Verifies `state`, requires the `activity:read_all` scope, exchanges the code for "
        "tokens, stores the athlete with encrypted tokens and enqueues the initial backfill. "
        "If the login carried an allowlisted `return_to`, the browser is redirected (303) there "
        "with `connected=1`, or with `connect_error=<reason>` once the state itself is valid."
    ),
    response_model=ConnectedResponse,
    responses={
        303: {
            "description": "Back to the allowlisted `return_to` (`connected=1` or `connect_error`)"
        },
        400: error(
            "Bad state, denied access, missing scope or bad code", "invalid or expired state"
        ),
        409: error(
            "The Strava account belongs to another user, or yours is still connected",
            "this Strava account is connected to another user",
        ),
    },
)
async def callback(
    settings: SettingsDep,
    clock: ClockDep,
    sessionmaker: SessionmakerDep,
    cipher: CipherDep,
    strava: StravaDep,
    queue: JobQueueDep,
    state: Annotated[str, Query()] = "",
    code: Annotated[str | None, Query()] = None,
    scope: Annotated[str, Query()] = "",
    error: Annotated[str | None, Query()] = None,
) -> ConnectedResponse | RedirectResponse:
    try:
        user_id, signed_return_to = parse_state_data(
            verify_state(state, clock(), settings.state_signing_key)
        )
    except InvalidStateError as exc:
        raise _bad_request("invalid or expired state") from exc
    # Re-checked against the current allowlist: the signature proves origin, not current policy.
    return_to = allowed_return_to(signed_return_to, settings)
    try:
        if error is not None:
            raise _bad_request(f"strava authorization failed: {error}")
        if code is None:
            raise _bad_request("missing code")
        if REQUIRED_SCOPE not in scope.split(","):
            raise _bad_request(f"the '{REQUIRED_SCOPE}' scope is required to sync activities")
        try:
            token = await strava.exchange_code(code)
        except StravaAuthError as exc:
            raise _bad_request("strava rejected the authorization code") from exc
        if token.athlete is None:
            raise _bad_request("strava did not return the athlete")
    except HTTPException as exc:
        if return_to:
            return _redirect(return_to, connect_error=str(exc.detail))
        raise

    try:
        async with sessionmaker.begin() as session:
            athlete_id = await AthleteRepository(session).upsert_connected(
                token.athlete.id, user_id
            )
            await TokenRepository(session, cipher).upsert(
                athlete_id, token.access_token, token.refresh_token, token.expires_at, scope
            )
    except AthleteTakenError as exc:
        log.warning("oauth_athlete_taken", user_id=user_id)
        if return_to:
            return _redirect(return_to, connect_error=str(exc))
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    queued = await queue.enqueue_backfill(athlete_id)
    log.info("athlete_connected", athlete_id=athlete_id, backfill_enqueued=queued)
    if return_to:
        return _redirect(return_to, connected="1")
    return ConnectedResponse(
        athlete_id=athlete_id, strava_athlete_id=token.athlete.id, backfill="queued"
    )


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def allowed_return_to(value: str | None, settings: Settings) -> str:
    """`value` if it exactly matches an allowlisted URL, else "" (no partial or prefix match)."""
    if value and value in settings.oauth_return_to_allowlist:
        return value
    return ""


def _redirect(url: str, **params: str) -> RedirectResponse:
    parts = urlsplit(url)
    query = "&".join(filter(None, [parts.query, urlencode(params)]))
    target = urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------- /v1/me/strava


@me_router.get("", summary="My Strava connection", response_model=StravaConnection)
async def connection(principal: CurrentUser, sessionmaker: SessionmakerDep) -> StravaConnection:
    async with sessionmaker() as session:
        athlete = await AthleteRepository(session).for_user(principal.user_id)
    if athlete is None or not athlete.active:
        return StravaConnection(connected=False)
    return StravaConnection(
        connected=True,
        athlete_id=athlete.id,
        strava_athlete_id=athlete.strava_athlete_id,
        connected_at=athlete.created_at,
    )


@me_router.post(
    "/authorize-url",
    summary="Start connecting Strava",
    description=(
        "The Strava authorize URL with a signed state naming you; the web BFF sends the browser "
        "there. `return_to` must match `OAUTH_RETURN_TO_ALLOWLIST` exactly, else it is ignored."
    ),
    response_model=AuthorizeUrl,
)
async def create_authorize_url(
    principal: CurrentUser,
    settings: SettingsDep,
    clock: ClockDep,
    return_to: Annotated[str | None, Query(examples=["http://localhost:3000/sync"])] = None,
) -> AuthorizeUrl:
    allowed = allowed_return_to(return_to, settings)
    return AuthorizeUrl(url=authorize_url(settings, clock(), principal.user_id, allowed))


@me_router.delete(
    "",
    summary="Disconnect Strava",
    description=(
        "Stops syncing at once; the worker then revokes the app at Strava and deletes the "
        "athlete's tokens and activities."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: error("No Strava account connected", "strava is not connected")},
)
async def disconnect(
    principal: CurrentUser, sessionmaker: SessionmakerDep, queue: JobQueueDep
) -> Response:
    async with sessionmaker.begin() as session:
        athletes = AthleteRepository(session)
        athlete = await athletes.for_user(principal.user_id)
        if athlete is None or not athlete.active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "strava is not connected")
        await athletes.set_active(athlete.id, active=False)
    await queue.enqueue_strava_disconnect(athlete.id)
    log.info("athlete_disconnect_requested", athlete_id=athlete.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
