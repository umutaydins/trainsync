"""OAuth connect: redirect to Strava, handle the callback, store tokens, enqueue a backfill."""

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from trainsync.api.deps import (
    CipherDep,
    ClockDep,
    JobQueueDep,
    SessionmakerDep,
    SettingsDep,
    StravaDep,
)
from trainsync.core.logging import get_logger
from trainsync.core.state import InvalidStateError, sign_state, verify_state
from trainsync.db.repositories.athletes import AthleteRepository
from trainsync.db.repositories.tokens import TokenRepository
from trainsync.strava.errors import StravaAuthError

router = APIRouter(prefix="/auth/strava", tags=["auth"])
log = get_logger(__name__)

REQUESTED_SCOPE = "read,activity:read_all"
REQUIRED_SCOPE = "activity:read_all"


class ConnectedResponse(BaseModel):
    athlete_id: int
    strava_athlete_id: int
    backfill: str


@router.get(
    "/login",
    summary="Start the Strava OAuth flow",
    description="Redirects the browser to Strava's authorize page with a signed, expiring `state`.",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
)
async def login(settings: SettingsDep, clock: ClockDep) -> RedirectResponse:
    query = urlencode(
        {
            "client_id": settings.strava_client_id,
            "redirect_uri": settings.strava_redirect_uri,
            "response_type": "code",
            "approval_prompt": "auto",
            "scope": REQUESTED_SCOPE,
            "state": sign_state(clock(), settings.state_signing_key),
        }
    )
    url = f"{settings.strava_oauth_public_base_url}/authorize?{query}"
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@router.get(
    "/callback",
    summary="Strava OAuth callback",
    description=(
        "Verifies `state`, requires the `activity:read_all` scope, exchanges the code for "
        "tokens, stores the athlete with encrypted tokens and enqueues the initial backfill."
    ),
    response_model=ConnectedResponse,
    responses={400: {"description": "Bad state, denied access, missing scope or bad code"}},
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
) -> ConnectedResponse:
    try:
        verify_state(state, clock(), settings.state_signing_key)
    except InvalidStateError as exc:
        raise _bad_request("invalid or expired state") from exc
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

    async with sessionmaker.begin() as session:
        athlete_id = await AthleteRepository(session).upsert_connected(token.athlete.id)
        await TokenRepository(session, cipher).upsert(
            athlete_id, token.access_token, token.refresh_token, token.expires_at, scope
        )

    queued = await queue.enqueue_backfill(athlete_id)
    log.info("athlete_connected", athlete_id=athlete_id, backfill_enqueued=queued)
    return ConnectedResponse(
        athlete_id=athlete_id, strava_athlete_id=token.athlete.id, backfill="queued"
    )


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
