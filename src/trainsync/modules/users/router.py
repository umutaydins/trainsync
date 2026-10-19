"""`/v1/me`: the signed-in user's profile, password, sessions and settings."""

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import JSONResponse

from trainsync.core.deps import ClockDep, JobQueueDep, SessionmakerDep, SettingsDep
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.core.security import verify_password
from trainsync.core.settings import Settings
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
from trainsync.modules.users.export import export_user
from trainsync.modules.users.lifecycle import delete_account
from trainsync.modules.users.models import UserSettings
from trainsync.modules.users.schemas import (
    EXPORT_EXAMPLE,
    DeleteAccountIn,
    SettingsOut,
    SettingsPatch,
)
from trainsync.modules.users.settings import FIELDS, UserSettingsRepository, effective

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


@router.get("/settings", summary="My settings", response_model=SettingsOut)
async def get_settings(
    principal: CurrentUser, sessionmaker: SessionmakerDep, settings: SettingsDep
) -> SettingsOut:
    async with sessionmaker() as session:
        row = await UserSettingsRepository(session, principal.user_id).get()
    return settings_out(principal.user_id, principal.timezone, row, settings)


@router.patch(
    "/settings",
    summary="Change my settings",
    description="Only the fields sent change; `null` returns a field to the default.",
    response_model=SettingsOut,
)
async def patch_settings(
    body: SettingsPatch,
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> SettingsOut:
    changes: dict[str, object] = body.model_dump(exclude_unset=True)
    if changes.get("sugar_limit_g") is not None:
        changes["sugar_limit_g"] = Decimal(str(changes["sugar_limit_g"]))
    async with sessionmaker.begin() as session:
        row = await UserSettingsRepository(session, principal.user_id).update(changes, clock())
    return settings_out(principal.user_id, principal.timezone, row, settings)


def settings_out(
    user_id: int, timezone: str, row: UserSettings | None, settings: Settings
) -> SettingsOut:
    custom = [name for name in FIELDS if row is not None and getattr(row, name) is not None]
    return SettingsOut.build(effective(user_id, timezone, row, settings), custom)


@router.get(
    "/export",
    summary="Export all my data",
    description="Every row you own as one JSON document (KVKK / GDPR). Secrets are left out.",
    responses={200: {"content": {"application/json": {"example": EXPORT_EXAMPLE}}}},
)
async def export(
    principal: CurrentUser, sessionmaker: SessionmakerDep, clock: ClockDep
) -> JSONResponse:
    async with sessionmaker() as session:
        document = await export_user(session, principal.user_id, clock())
    return JSONResponse(
        document,
        headers={"Content-Disposition": 'attachment; filename="trainsync-export.json"'},
    )


@router.delete(
    "",
    summary="Delete my account",
    description=(
        "Needs the password. Signs out everywhere and unlinks Telegram at once; a background "
        "job then revokes Strava and deletes every row of the account. The owner account "
        "cannot be deleted here."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: error("Wrong password", "the password is wrong"),
        403: error("The owner account", "the owner account cannot be deleted"),
    },
)
async def delete_me(
    body: DeleteAccountIn,
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    queue: JobQueueDep,
) -> Response:
    if principal.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "the owner account cannot be deleted")
    async with sessionmaker() as session:
        user = await UserRepository(session).by_id(principal.user_id)
    if user is None or not await verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "the password is wrong")
    async with sessionmaker.begin() as session:
        await delete_account(session, principal.user_id, clock())
    await queue.enqueue_purge_user(principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
