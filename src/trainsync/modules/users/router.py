"""`/v1/me`: the signed-in user's profile, password and sessions."""

from fastapi import APIRouter, HTTPException, Response, status

from trainsync.core.deps import ClockDep, SessionmakerDep
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.modules.auth import service
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.auth.errors import AuthError
from trainsync.modules.auth.repository import UserRepository
from trainsync.modules.auth.router import http_error
from trainsync.modules.auth.schemas import (
    MeOut,
    MePatch,
    PasswordChangeIn,
    SessionList,
    SessionOut,
)

router = APIRouter(prefix="/v1/me", tags=["me"], responses=UNAUTHORIZED)

NOT_FOUND = error("No such session of yours", "session not found")


@router.get("", summary="Who am I", response_model=MeOut)
async def me(principal: CurrentUser, sessionmaker: SessionmakerDep) -> MeOut:
    async with sessionmaker() as session:
        user = await UserRepository(session).by_id(principal.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "the account no longer exists")
    return MeOut.from_row(user)


@router.patch(
    "",
    summary="Change the display name or time zone",
    response_model=MeOut,
    responses={400: error("Unknown time zone", "unknown time zone 'Mars/Base'")},
)
async def patch_me(body: MePatch, principal: CurrentUser, sessionmaker: SessionmakerDep) -> MeOut:
    try:
        zone = service.valid_timezone(body.timezone) if body.timezone else None
    except AuthError as exc:
        raise http_error(exc) from exc
    async with sessionmaker.begin() as session:
        users = UserRepository(session)
        await users.update_profile(principal.user_id, display_name=body.display_name, timezone=zone)
        user = await users.by_id(principal.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "the account no longer exists")
    return MeOut.from_row(user)


@router.post(
    "/password",
    summary="Change the password",
    description="Needs the current password. Every other session of the account ends.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: error("Current password wrong", "the current password is wrong"),
        422: error("New password too short or long", "password must be at least 10 characters"),
    },
)
async def change_password(
    body: PasswordChangeIn, principal: CurrentUser, sessionmaker: SessionmakerDep, clock: ClockDep
) -> Response:
    try:
        await service.change_password(
            sessionmaker, clock, principal, current=body.current_password, new=body.new_password
        )
    except AuthError as exc:
        raise http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions", summary="My signed-in sessions", response_model=SessionList)
async def sessions(
    principal: CurrentUser, sessionmaker: SessionmakerDep, clock: ClockDep
) -> SessionList:
    rows = await service.sessions_of(sessionmaker, clock, principal.user_id)
    return SessionList(
        items=[
            SessionOut(
                id=row.id,
                user_agent=row.user_agent,
                created_at=row.created_at,
                last_seen_at=row.last_seen_at,
                expires_at=row.expires_at,
                current=row.id == principal.session_id,
            )
            for row in rows
        ]
    )


@router.delete(
    "/sessions/{session_id}",
    summary="Sign out one session",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: NOT_FOUND},
)
async def revoke_session(
    session_id: int, principal: CurrentUser, sessionmaker: SessionmakerDep, clock: ClockDep
) -> Response:
    if not await service.revoke_session(sessionmaker, clock, principal.user_id, session_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
