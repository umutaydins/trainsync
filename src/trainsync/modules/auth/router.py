"""`/v1/auth`: register, sign in, sign out, reset a password (ADR 0034)."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response, status

from trainsync.core.deps import ClockDep, RedisDep, SessionmakerDep, SettingsDep
from trainsync.core.errors import UNAUTHORIZED, Responses, error
from trainsync.modules.auth import service
from trainsync.modules.auth.dependencies import ClientAddress, CurrentUser
from trainsync.modules.auth.errors import AuthError
from trainsync.modules.auth.limits import AuthLimiter
from trainsync.modules.auth.schemas import (
    LoginIn,
    MeOut,
    RegisterIn,
    RegistrationOut,
    ResetIn,
    SessionTokenOut,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])

RATE_LIMITED: Responses = {
    429: error("Too many attempts; see `Retry-After`", "too many failed sign-ins; try again later")
}


def http_error(exc: AuthError) -> HTTPException:
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
    return HTTPException(exc.status_code, exc.detail, headers=headers)


@router.get(
    "/registration",
    summary="How accounts are created",
    description="`invite` (an invite code is needed), `open` or `closed`. No auth.",
    response_model=RegistrationOut,
)
async def registration(settings: SettingsDep) -> RegistrationOut:
    return RegistrationOut(mode=settings.registration_mode)


@router.post(
    "/register",
    summary="Create an account",
    response_model=MeOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        **RATE_LIMITED,
        400: error("Invite missing, used or expired", "an invite code is required"),
        403: error("REGISTRATION_MODE=closed", "registration is closed"),
        409: error("Email already registered", "an account with this email already exists"),
    },
)
async def register(
    body: RegisterIn,
    sessionmaker: SessionmakerDep,
    settings: SettingsDep,
    clock: ClockDep,
    redis: RedisDep,
    address: ClientAddress,
) -> MeOut:
    try:
        user = await service.register(
            sessionmaker,
            settings,
            clock,
            AuthLimiter(redis, clock, settings),
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            timezone=body.timezone,
            invite_code=body.invite_code,
            address=address,
        )
    except AuthError as exc:
        raise http_error(exc) from exc
    return MeOut.from_row(user)


@router.post(
    "/login",
    summary="Sign in",
    description=(
        "Returns a session token for `Authorization: Bearer`. After `LOGIN_MAX_FAILURES` failures "
        "for one email the email is locked for `LOGIN_LOCKOUT_MINUTES`, right password or not."
    ),
    response_model=SessionTokenOut,
    responses={**RATE_LIMITED, 401: error("Wrong email or password", service.INVALID_LOGIN)},
)
async def login(
    body: LoginIn,
    sessionmaker: SessionmakerDep,
    settings: SettingsDep,
    clock: ClockDep,
    redis: RedisDep,
    address: ClientAddress,
    user_agent: Annotated[str | None, Header()] = None,
) -> SessionTokenOut:
    try:
        issued = await service.login(
            sessionmaker,
            settings,
            clock,
            AuthLimiter(redis, clock, settings),
            email=body.email,
            password=body.password,
            user_agent=user_agent,
            address=address,
        )
    except AuthError as exc:
        raise http_error(exc) from exc
    return SessionTokenOut(
        token=issued.token, expires_at=issued.expires_at, user=MeOut.from_row(issued.user)
    )


@router.post(
    "/logout",
    summary="Sign out (revoke this session)",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=UNAUTHORIZED,
)
async def logout(
    principal: CurrentUser, sessionmaker: SessionmakerDep, clock: ClockDep
) -> Response:
    await service.logout(sessionmaker, clock, principal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/reset",
    summary="Set a new password with a reset link's token",
    description="The token comes from a link the owner generated. Every session of the user ends.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        400: error("Unknown, used or expired token", "the reset link is invalid, used or expired")
    },
)
async def reset(body: ResetIn, sessionmaker: SessionmakerDep, clock: ClockDep) -> Response:
    try:
        await service.reset_password(sessionmaker, clock, token=body.token, new=body.password)
    except AuthError as exc:
        raise http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
