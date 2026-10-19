"""`/v1/admin`: owner only. Account facts, never a user's training or body data."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, status

from trainsync.core.deps import ClockDep, SessionmakerDep, SettingsDep
from trainsync.core.errors import FORBIDDEN_OWNER, UNAUTHORIZED, error
from trainsync.modules.auth import service
from trainsync.modules.auth.dependencies import OwnerUser
from trainsync.modules.auth.errors import AuthError
from trainsync.modules.auth.links import invite_link, reset_link
from trainsync.modules.auth.models import Invite, UserRole
from trainsync.modules.auth.repository import InviteRepository, UserRepository
from trainsync.modules.auth.schemas import (
    AdminUserList,
    AdminUserOut,
    InviteCreated,
    InviteIn,
    InviteList,
    InviteOut,
    InviteStatus,
    ResetLinkOut,
)

router = APIRouter(
    prefix="/v1/admin", tags=["admin"], responses={**UNAUTHORIZED, **FORBIDDEN_OWNER}
)


def invite_status(invite: Invite, now: datetime) -> InviteStatus:
    if invite.used_at is not None:
        return "used"
    if invite.revoked_at is not None:
        return "revoked"
    return "expired" if invite.expires_at <= now else "open"


def _invite_out(invite: Invite, now: datetime) -> InviteOut:
    return InviteOut(
        id=invite.id,
        note=invite.note,
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        used_at=invite.used_at,
        revoked_at=invite.revoked_at,
        status=invite_status(invite, now),
    )


@router.post(
    "/invites",
    summary="Create an invite",
    description="The code is shown once; the link opens the dashboard's register page.",
    response_model=InviteCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_invite(
    body: InviteIn,
    owner: OwnerUser,
    sessionmaker: SessionmakerDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> InviteCreated:
    invite, code = await service.create_invite(
        sessionmaker, settings, clock, created_by=owner.user_id, note=body.note
    )
    return InviteCreated(
        **_invite_out(invite, clock()).model_dump(), code=code, url=invite_link(settings, code)
    )


@router.get("/invites", summary="List invites", response_model=InviteList)
async def list_invites(
    owner: OwnerUser, sessionmaker: SessionmakerDep, clock: ClockDep
) -> InviteList:
    now = clock()
    async with sessionmaker() as session:
        rows = await InviteRepository(session).all()
    return InviteList(items=[_invite_out(row, now) for row in rows])


@router.delete(
    "/invites/{invite_id}",
    summary="Revoke an unused invite",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: error("No open invite with this id", "invite not found")},
)
async def revoke_invite(
    invite_id: int, owner: OwnerUser, sessionmaker: SessionmakerDep, clock: ClockDep
) -> Response:
    async with sessionmaker.begin() as session:
        revoked = await InviteRepository(session).revoke(invite_id, clock())
    if not revoked:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invite not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users", summary="List accounts", response_model=AdminUserList)
async def list_users(owner: OwnerUser, sessionmaker: SessionmakerDep) -> AdminUserList:
    async with sessionmaker() as session:
        rows = await UserRepository(session).active()
    return AdminUserList(
        items=[
            AdminUserOut(
                id=u.id,
                email=u.email,
                display_name=u.display_name,
                role=UserRole(u.role),
                created_at=u.created_at,
            )
            for u in rows
        ]
    )


@router.post(
    "/users/{user_id}/reset-link",
    summary="Generate a one-time password reset link",
    response_model=ResetLinkOut,
    responses={404: error("No such account", "no such user")},
)
async def create_reset_link(
    user_id: int,
    owner: OwnerUser,
    sessionmaker: SessionmakerDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> ResetLinkOut:
    try:
        token, expires_at = await service.create_reset(sessionmaker, settings, clock, user_id)
    except AuthError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.detail) from exc
    return ResetLinkOut(url=reset_link(settings, token), expires_at=expires_at)
