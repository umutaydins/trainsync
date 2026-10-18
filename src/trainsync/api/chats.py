"""`/v1/chats/{chat_id}/settings`: per-chat bot settings for the bot process (ADR 0031).

The bot never touches the database: `/lang` stores the choice here, and the bot reads it back
after a restart. `lang` is null when the chat never chose one (the bot uses `BOT_LANG`).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict, Field

from trainsync.api.deps import ClockDep, SessionmakerDep, require_api_key
from trainsync.api.errors import UNAUTHORIZED
from trainsync.core.settings import BotLang
from trainsync.db.repositories.chat_settings import ChatSettingsRepository

router = APIRouter(prefix="/v1/chats", tags=["chats"], dependencies=[Depends(require_api_key)])


class ChatSettingsOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"chat_id": 123456789, "lang": "tr"}]}
    )

    chat_id: int
    lang: BotLang | None = Field(description="null: never chosen, the bot uses BOT_LANG")


class ChatSettingsIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"lang": "en"}]})

    lang: BotLang


ChatId = Annotated[int, Path(examples=[123456789], description="Telegram chat id")]


@router.get(
    "/{chat_id}/settings",
    summary="Settings of a chat",
    description="The language the chat chose with `/lang`, or null.",
    response_model=ChatSettingsOut,
    responses={**UNAUTHORIZED},
)
async def get_chat_settings(sessionmaker: SessionmakerDep, chat_id: ChatId) -> ChatSettingsOut:
    async with sessionmaker() as session:
        lang = await ChatSettingsRepository(session).lang(chat_id)
    return ChatSettingsOut(chat_id=chat_id, lang=lang)


@router.put(
    "/{chat_id}/settings",
    summary="Store the settings of a chat",
    description="Idempotent: the same body twice stores one row.",
    response_model=ChatSettingsOut,
    responses={**UNAUTHORIZED},
)
async def put_chat_settings(
    sessionmaker: SessionmakerDep, clock: ClockDep, chat_id: ChatId, body: ChatSettingsIn
) -> ChatSettingsOut:
    async with sessionmaker.begin() as session:
        await ChatSettingsRepository(session).set_lang(chat_id, body.lang, clock())
    return ChatSettingsOut(chat_id=chat_id, lang=body.lang)
