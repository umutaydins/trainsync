"""`/v1/chats/{chat_id}/settings`: per-chat bot settings for the bot process (ADR 0031, 0032).

The bot never touches the database: `/lang` and `/swear` store the choice here, and the bot
reads it back after a restart. A null field means the chat never chose (the bot uses
`BOT_LANG` / `BOT_PROFANITY`).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict, Field, model_validator

from trainsync.core.deps import ClockDep, SessionmakerDep, require_api_key
from trainsync.core.errors import UNAUTHORIZED
from trainsync.core.settings import BotLang, BotProfanity
from trainsync.modules.chat.repository import ChatSettingsRepository

router = APIRouter(prefix="/v1/chats", tags=["chats"], dependencies=[Depends(require_api_key)])


class ChatSettingsOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"chat_id": 123456789, "lang": "tr", "profanity": "max"}]}
    )

    chat_id: int
    lang: BotLang | None = Field(description="null: never chosen, the bot uses BOT_LANG")
    profanity: BotProfanity | None = Field(
        default=None, description="null: never chosen, the bot uses BOT_PROFANITY"
    )


class ChatSettingsIn(BaseModel):
    """Either field or both; a field left out keeps its stored value."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"lang": "en"}, {"profanity": "max"}]}
    )

    lang: BotLang | None = None
    profanity: BotProfanity | None = None

    @model_validator(mode="after")
    def _something(self) -> "ChatSettingsIn":
        if self.lang is None and self.profanity is None:
            raise ValueError("give lang, profanity or both")
        return self


ChatId = Annotated[int, Path(examples=[123456789], description="Telegram chat id")]


@router.get(
    "/{chat_id}/settings",
    summary="Settings of a chat",
    description="The language (`/lang`) and profanity level (`/swear`) the chat chose, or null.",
    response_model=ChatSettingsOut,
    responses={**UNAUTHORIZED},
)
async def get_chat_settings(sessionmaker: SessionmakerDep, chat_id: ChatId) -> ChatSettingsOut:
    async with sessionmaker() as session:
        prefs = await ChatSettingsRepository(session).get(chat_id)
    return ChatSettingsOut(chat_id=chat_id, lang=prefs.lang, profanity=prefs.profanity)


@router.put(
    "/{chat_id}/settings",
    summary="Store the settings of a chat",
    description=(
        "Idempotent: the same body twice stores one row. A field left out keeps its stored "
        "value; at least one is required."
    ),
    response_model=ChatSettingsOut,
    responses={**UNAUTHORIZED},
)
async def put_chat_settings(
    sessionmaker: SessionmakerDep, clock: ClockDep, chat_id: ChatId, body: ChatSettingsIn
) -> ChatSettingsOut:
    async with sessionmaker.begin() as session:
        prefs = await ChatSettingsRepository(session).set(
            chat_id, clock(), lang=body.lang, profanity=body.profanity
        )
    return ChatSettingsOut(chat_id=chat_id, lang=prefs.lang, profanity=prefs.profanity)
