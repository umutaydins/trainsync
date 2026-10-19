"""`/v1/telegram/chats/*` and `/v1/me/settings` backed by dicts: who a chat belongs to and their
settings, as far as the bot can tell (ADR 0036). Defaults come from a `Settings`, like the API's
`effective()`."""

import json
import re
from typing import Any

import httpx
import respx
from pydantic import SecretStr

from tests.conftest import make_settings
from trainsync.core.clock import Clock
from trainsync.core.settings import BotLang, BotProfanity, Settings
from trainsync.modules.chat.links import ChatLinks
from trainsync.modules.chat.read_api import ReadApi
from trainsync.modules.users.models import UserSettings
from trainsync.modules.users.settings import FIELDS, effective

OWNER = 1
SETTING_NAMES = FIELDS


class ChatLinksApi:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or make_settings()
        self.chats: dict[int, int] = {}  # chat id → user id
        self.users: dict[int, dict[str, Any]] = {}  # user id → stored overrides
        self.names: dict[int, str] = {}
        self.codes: dict[str, int] = {}
        self.reads = 0
        self.down = False

    def link(self, chat_id: int, user_id: int = OWNER, **overrides: Any) -> "ChatLinksApi":
        self.chats[chat_id] = user_id
        self.users.setdefault(user_id, {}).update(overrides)
        self.names.setdefault(user_id, f"User {user_id}")
        return self

    def stored(self, chat_id: int) -> dict[str, Any]:
        return self.users.get(self.chats.get(chat_id, -1), {})

    def lang(self, chat_id: int) -> BotLang | None:
        value = self.stored(chat_id).get("lang")
        return "tr" if value == "tr" else "en" if value == "en" else None

    def profanity(self, chat_id: int) -> BotProfanity | None:
        value = self.stored(chat_id).get("profanity")
        return "max" if value == "max" else "roast" if value == "roast" else None

    def settings_json(self, user_id: int) -> dict[str, Any]:
        stored = self.users.get(user_id, {})
        row = UserSettings(user_id=user_id, **{name: stored.get(name) for name in SETTING_NAMES})
        zone = stored.get("timezone", self.settings.checkin_tz)
        values = effective(user_id, zone, row, self.settings)
        out = {
            name: getattr(values, name) for name in (*SETTING_NAMES, "emergency_number", "timezone")
        }
        for key in ("checkin_time", "workout_reminder_time"):
            out[key] = out[key].isoformat()
        out["custom"] = [name for name in SETTING_NAMES if stored.get(name) is not None]
        return out

    def owner_json(self, chat_id: int) -> dict[str, Any]:
        user_id = self.chats[chat_id]
        return {
            "chat_id": chat_id,
            "user_id": user_id,
            "display_name": self.names[user_id],
            "role": "owner" if user_id == OWNER else "user",
            "settings": self.settings_json(user_id),
        }

    def get(self, request: httpx.Request, chat_id: str) -> httpx.Response:
        self.reads += 1
        if self.down:
            return httpx.Response(503, json={"detail": "down"})
        if int(chat_id) not in self.chats:
            return httpx.Response(404, json={"detail": "chat not linked"})
        return httpx.Response(200, json=self.owner_json(int(chat_id)))

    def post_link(self, request: httpx.Request, chat_id: str) -> httpx.Response:
        user_id = self.codes.pop(json.loads(request.content)["code"].upper(), None)
        if user_id is None:
            return httpx.Response(400, json={"detail": "invalid or expired code"})
        for chat, owner in list(self.chats.items()):
            if owner == user_id:
                del self.chats[chat]
        self.link(int(chat_id), user_id)
        return httpx.Response(200, json=self.owner_json(int(chat_id)))

    def delete(self, request: httpx.Request, chat_id: str) -> httpx.Response:
        if self.chats.pop(int(chat_id), None) is None:
            return httpx.Response(404, json={"detail": "chat not linked"})
        return httpx.Response(204)

    def patch_settings(self, request: httpx.Request) -> httpx.Response:
        user_id = int(request.headers["X-Acting-User"])
        self.users.setdefault(user_id, {}).update(json.loads(request.content))
        return httpx.Response(200, json=self.settings_json(user_id))

    def install(self, router: respx.MockRouter, api: str) -> "ChatLinksApi":
        chat = rf"{re.escape(api)}/v1/telegram/chats/(?P<chat_id>-?\d+)"
        router.get(url__regex=rf"{chat}$").mock(side_effect=self.get)
        router.post(url__regex=rf"{chat}/link$").mock(side_effect=self.post_link)
        router.delete(url__regex=rf"{chat}$").mock(side_effect=self.delete)
        router.patch(f"{api}/v1/me/settings").mock(side_effect=self.patch_settings)
        return self


def chat_links(http: httpx.AsyncClient, api: str, clock: Clock) -> ChatLinks:
    """The bot's `ChatLinks` without a cache, so every update sees the fake's current state."""
    return ChatLinks(ReadApi(http, api, SecretStr("bot-key")), clock, ttl_s=0)
