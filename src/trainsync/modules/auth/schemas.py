"""Request and response bodies of `/v1/auth`, `/v1/me` and `/v1/admin`."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from trainsync.core.security import PASSWORD_MAX_LENGTH
from trainsync.modules.auth.models import User, UserRole

Password = Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)]
# Stripped first: a name of only spaces is no name (the app would show an empty sidebar).
DisplayName = Annotated[
    str, StringConstraints(strip_whitespace=True), Field(min_length=1, max_length=100)
]
TimeZone = Annotated[str, Field(min_length=1, max_length=64, examples=["Europe/Berlin"])]

ME_EXAMPLE: dict[str, Any] = {
    "id": 2,
    "email": "runner@example.com",
    "display_name": "Runner",
    "role": "user",
    "timezone": "Europe/Berlin",
    "created_at": "2026-10-19T08:00:00Z",
}

SESSION_EXAMPLE: dict[str, Any] = {
    "id": 12,
    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X)",
    "created_at": "2026-10-19T08:00:00Z",
    "last_seen_at": "2026-10-19T09:30:00Z",
    "expires_at": "2026-11-18T09:30:00Z",
    "current": True,
}
INVITE_EXAMPLE: dict[str, Any] = {
    "id": 3,
    "note": "for my training partner",
    "created_at": "2026-10-19T08:00:00Z",
    "expires_at": "2026-10-26T08:00:00Z",
    "used_at": None,
    "revoked_at": None,
    "status": "open",
}


class MeOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [ME_EXAMPLE]})

    id: int
    email: str
    display_name: str
    role: UserRole
    timezone: str
    created_at: datetime

    @classmethod
    def from_row(cls, user: User) -> "MeOut":
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=UserRole(user.role),
            timezone=user.timezone,
            created_at=user.created_at,
        )


class RegisterIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "email": "runner@example.com",
                    "password": "correct horse battery",
                    "display_name": "Runner",
                    "timezone": "Europe/Berlin",
                    "invite_code": "Xr2…",
                }
            ]
        }
    )

    email: EmailStr
    password: Password
    display_name: DisplayName | None = None
    timezone: TimeZone | None = Field(default=None, description="IANA zone; default CHECKIN_TZ")
    invite_code: Annotated[str, Field(max_length=100)] | None = Field(
        default=None, description="Required unless REGISTRATION_MODE=open"
    )


class LoginIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"email": "runner@example.com", "password": "correct horse battery"}]
        }
    )

    email: Annotated[str, Field(min_length=1, max_length=320)]
    password: Password


class SessionTokenOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"token": "q9c…", "expires_at": "2026-11-18T08:00:00Z", "user": ME_EXAMPLE}
            ]
        }
    )

    token: str = Field(description="Send as `Authorization: Bearer <token>`; shown only once")
    expires_at: datetime
    user: MeOut


class ResetIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"token": "Zt4…", "password": "a brand new password"}]}
    )

    token: Annotated[str, Field(min_length=1, max_length=100)]
    password: Password


class RegistrationOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"mode": "invite"}]})

    mode: Literal["invite", "open", "closed"]


class MePatch(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"display_name": "Runner", "timezone": "Europe/Berlin"}]}
    )

    display_name: DisplayName | None = None
    timezone: TimeZone | None = None


class PasswordChangeIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "current_password": "correct horse battery",
                    "new_password": "a brand new password",
                }
            ]
        }
    )

    current_password: Password
    new_password: Password


class SessionOut(BaseModel):
    id: int
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    current: bool = Field(description="The session this request was made with")


class SessionList(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [SESSION_EXAMPLE]}]})

    items: list[SessionOut]


class InviteIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"note": "for my training partner"}]})

    note: Annotated[str, Field(max_length=200)] | None = None


InviteStatus = Literal["open", "used", "revoked", "expired"]


class InviteOut(BaseModel):
    id: int
    note: str | None
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None
    revoked_at: datetime | None
    status: InviteStatus


class InviteCreated(InviteOut):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    **INVITE_EXAMPLE,
                    "code": "Xr2…",
                    "url": "https://dashboard.example/register?invite=Xr2…",
                }
            ]
        }
    )

    code: str = Field(description="Shown only once")
    url: str


class InviteList(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [INVITE_EXAMPLE]}]})

    items: list[InviteOut]


class AdminUserOut(BaseModel):
    """Account facts only: the owner never sees a user's training data."""

    id: int
    email: str
    display_name: str
    role: UserRole
    created_at: datetime


class AdminUserList(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"items": [{k: v for k, v in ME_EXAMPLE.items() if k != "timezone"}]}]
        }
    )

    items: list[AdminUserOut]


class ResetLinkOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "url": "https://dashboard.example/reset-password?token=Zt4…",
                    "expires_at": "2026-10-19T09:00:00Z",
                }
            ]
        }
    )

    url: str
    expires_at: datetime
