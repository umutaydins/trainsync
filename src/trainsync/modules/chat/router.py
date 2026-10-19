"""Telegram linking (ADR 0036).

- `/v1/me/telegram`: the signed-in user gets a one-time code, sees and removes their link.
- `/v1/telegram/chats/{chat_id}`: the bot (a service key, ADR 0036) looks up who a chat
  belongs to with their settings, redeems a `/link CODE` and unlinks on `/unlink`.
"""

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from pydantic import BaseModel, ConfigDict, Field

from trainsync.core.deps import ClockDep, RedisDep, SessionmakerDep, SettingsDep
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.core.settings import Settings
from trainsync.modules.auth.dependencies import CurrentUser, require_service_key
from trainsync.modules.auth.models import UserRole
from trainsync.modules.auth.repository import UserRepository
from trainsync.modules.chat.repository import LinkCodes, TelegramChatRepository
from trainsync.modules.users.router import settings_out
from trainsync.modules.users.schemas import SETTINGS_EXAMPLE, SettingsOut
from trainsync.modules.users.settings import UserSettingsRepository

me_router = APIRouter(prefix="/v1/me/telegram", tags=["me"], responses=UNAUTHORIZED)
service_router = APIRouter(
    prefix="/v1/telegram/chats",
    tags=["chats"],
    dependencies=[Depends(require_service_key)],
    responses={**UNAUTHORIZED, 403: error("Not a service key", "service key required")},
)

ChatId = Annotated[int, Path(examples=[123456789], description="Telegram chat id")]
TELEGRAM_LINK = "https://t.me/{bot}?start={code}"


class LinkStatus(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"linked": True, "linked_at": "2026-10-19T08:00:00Z"}, {"linked": False}]
        }
    )

    linked: bool
    linked_at: datetime | None = None


class LinkCode(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "code": "K7Q2M9XD",
                    "expires_at": "2026-10-19T08:10:00Z",
                    "command": "/link K7Q2M9XD",
                    "bot_url": "https://t.me/trainsync_bot?start=K7Q2M9XD",
                }
            ]
        }
    )

    code: str
    expires_at: datetime
    command: str = Field(description="What to send the bot")
    bot_url: str | None = Field(description="Opens the bot with the code; null without a username")


class LinkIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"code": "K7Q2M9XD"}]})

    code: Annotated[str, Field(min_length=4, max_length=16)]


class ChatOwner(BaseModel):
    """Who a linked chat belongs to and how the bot should speak to them."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "chat_id": 123456789,
                    "user_id": 2,
                    "display_name": "Runner",
                    "role": "user",
                    "settings": SETTINGS_EXAMPLE,
                }
            ]
        }
    )

    chat_id: int
    user_id: int
    display_name: str
    role: UserRole
    settings: SettingsOut


def _codes(redis: RedisDep, settings: Settings) -> LinkCodes:
    return LinkCodes(redis, settings.telegram_link_code_ttl_minutes * 60)


# ---------------------------------------------------------------- the user


@me_router.get("", summary="My Telegram link", response_model=LinkStatus)
async def link_status(principal: CurrentUser, sessionmaker: SessionmakerDep) -> LinkStatus:
    async with sessionmaker() as session:
        chat = await TelegramChatRepository(session).by_user(principal.user_id)
    return LinkStatus(linked=chat is not None, linked_at=chat.linked_at if chat else None)


@me_router.post(
    "/code",
    summary="A one-time code for /link",
    description="Send `/link CODE` to the bot within `TELEGRAM_LINK_CODE_TTL_MINUTES`.",
    response_model=LinkCode,
)
async def link_code(
    principal: CurrentUser, redis: RedisDep, settings: SettingsDep, clock: ClockDep
) -> LinkCode:
    code = await _codes(redis, settings).issue(principal.user_id)
    bot = settings.telegram_bot_username.lstrip("@")
    return LinkCode(
        code=code,
        expires_at=clock() + timedelta(minutes=settings.telegram_link_code_ttl_minutes),
        command=f"/link {code}",
        bot_url=TELEGRAM_LINK.format(bot=bot, code=code) if bot else None,
    )


@me_router.delete(
    "",
    summary="Unlink my Telegram chat",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: error("No chat linked", "telegram is not linked")},
)
async def unlink_me(principal: CurrentUser, sessionmaker: SessionmakerDep) -> Response:
    async with sessionmaker.begin() as session:
        removed = await TelegramChatRepository(session).unlink_user(principal.user_id)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "telegram is not linked")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- the bot (service key)


@service_router.get(
    "/{chat_id}",
    summary="Who a chat belongs to",
    response_model=ChatOwner,
    responses={404: error("The chat is not linked", "chat not linked")},
)
async def chat_owner(
    chat_id: ChatId, sessionmaker: SessionmakerDep, settings: SettingsDep
) -> ChatOwner:
    async with sessionmaker() as session:
        chat = await TelegramChatRepository(session).by_chat(chat_id)
        user = await UserRepository(session).by_id(chat.user_id) if chat else None
        if chat is None or user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "chat not linked")
        row = await UserSettingsRepository(session, user.id).get()
    return ChatOwner(
        chat_id=chat_id,
        user_id=user.id,
        display_name=user.display_name,
        role=UserRole(user.role),
        settings=settings_out(user.id, user.timezone, row, settings),
    )


@service_router.post(
    "/{chat_id}/link",
    summary="Redeem a /link code",
    description="Binds the chat to the code's user; their previous chat is unlinked.",
    response_model=ChatOwner,
    responses={400: error("Unknown, used or expired code", "invalid or expired code")},
)
async def link_chat(
    chat_id: ChatId,
    body: LinkIn,
    sessionmaker: SessionmakerDep,
    settings: SettingsDep,
    redis: RedisDep,
    clock: ClockDep,
) -> ChatOwner:
    user_id = await _codes(redis, settings).redeem(body.code)
    if user_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired code")
    async with sessionmaker.begin() as session:
        if await UserRepository(session).by_id(user_id) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired code")
        await TelegramChatRepository(session).link(chat_id, user_id, clock())
    return await chat_owner(chat_id, sessionmaker, settings)


@service_router.delete(
    "/{chat_id}",
    summary="Unlink a chat (/unlink)",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: error("The chat is not linked", "chat not linked")},
)
async def unlink_chat(chat_id: ChatId, sessionmaker: SessionmakerDep) -> Response:
    async with sessionmaker.begin() as session:
        removed = await TelegramChatRepository(session).unlink_chat(chat_id)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "chat not linked")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
