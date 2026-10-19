"""`CurrentUser`: who a request acts as (ADR 0034, 0036).

- `Authorization: Bearer <session token>` → that session's user (the web BFF, apps).
- `X-API-Key` → the owner (machine and owner tooling), or, for a key in `SERVICE_API_KEYS` (the
  bot), the user named in `X-Acting-User`.
Anything else is 401. A route that serves user-owned data depends on `CurrentUser`.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from trainsync.core.deps import API_KEY_HEADER, ClockDep, SessionmakerDep, SettingsDep, key_matches
from trainsync.modules.auth.models import User, UserRole
from trainsync.modules.auth.repository import UserRepository
from trainsync.modules.auth.service import Principal, authenticate

ACTING_USER_HEADER = "X-Acting-User"
_bearer = HTTPBearer(auto_error=False, description="A session token from `POST /v1/auth/login`.")


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
    )


def _principal(user: User) -> Principal:
    return Principal(user.id, UserRole(user.role), user.timezone)


async def current_principal(
    settings: SettingsDep,
    clock: ClockDep,
    sessionmaker: SessionmakerDep,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
    api_key: Annotated[str | None, Security(API_KEY_HEADER)],
    acting_user: Annotated[
        int | None,
        Header(
            alias=ACTING_USER_HEADER,
            include_in_schema=False,
            description="Service keys only: the user the call acts as",
        ),
    ] = None,
) -> Principal:
    if bearer is not None:
        principal = await authenticate(sessionmaker, settings, clock, bearer.credentials)
        if principal is None:
            raise _unauthorized("the session is invalid or has expired")
        return principal
    if not key_matches(api_key, settings.all_api_keys):
        raise _unauthorized("sign in or send a valid API key")
    async with sessionmaker() as session:
        users = UserRepository(session)
        if acting_user is not None:
            if not key_matches(api_key, settings.service_api_keys):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN, f"this key may not send {ACTING_USER_HEADER}"
                )
            user = await users.by_id(acting_user)
            if user is None:
                raise _unauthorized("the acting user does not exist")
            return _principal(user)
        owner = await users.owner()
    if owner is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "no owner account yet: run scripts/owner.py set-password",
        )
    return _principal(owner)


def client_address(request: Request) -> str:
    """The caller's address: the first `X-Forwarded-For` hop (set by the gateway), else the
    socket peer. Only used for abuse limits, never for access decisions."""
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",", 1)[0].strip()
    if first:
        return first
    return request.client.host if request.client else "unknown"


CurrentUser = Annotated[Principal, Depends(current_principal)]
ClientAddress = Annotated[str, Depends(client_address)]


def require_service_key(
    settings: SettingsDep, api_key: Annotated[str | None, Security(API_KEY_HEADER)]
) -> None:
    """Only a key in `SERVICE_API_KEYS` (the bot's) may call service routes."""
    if not key_matches(api_key, settings.all_api_keys):
        raise _unauthorized("send a valid API key")
    if not key_matches(api_key, settings.service_api_keys):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "service key required")


def require_owner(principal: CurrentUser) -> Principal:
    if not principal.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "owner only")
    return principal


OwnerUser = Annotated[Principal, Depends(require_owner)]
