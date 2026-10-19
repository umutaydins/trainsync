"""Natural-language questions in the bot: Claude plans read-API calls, the API supplies every
number (ADR 0014).

The model only sees four tools, mapped 1:1 to read endpoints. Every tool call is validated here
(strict JSON schema on the API side, our own date and range checks on this side) before it runs;
invalid arguments go back to the model as an error result and are never executed. One question
gets at most `max_tool_calls` tool calls and `timeout_s` seconds in total, and each chat at most
`ASSISTANT_RATE_LIMIT_PER_HOUR` questions (counted in Redis).
"""

import asyncio
import json
import re
from datetime import date
from typing import Annotated

import anthropic
from anthropic.types.beta import (
    BetaMessage,
    BetaMessageParam,
    BetaToolResultBlockParam,
    BetaToolUseBlock,
)
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, model_validator

from trainsync.core.clock import Clock
from trainsync.core.logging import get_logger
from trainsync.core.settings import BotProfanity
from trainsync.integrations.anthropic.planner import Planner
from trainsync.integrations.anthropic.tools import (
    MAX_LIST_LIMIT,
    TOOLS,
)
from trainsync.modules.chat.assistant_limits import Asker, DailyQuota, RateLimiter, RedisRateLimiter
from trainsync.modules.chat.assistant_prompt import system_prompt
from trainsync.modules.chat.read_api import ReadApi, ReadApiError
from trainsync.modules.coach.guardrails import violations
from trainsync.modules.coach.mode import CURRENT_PROFANITY, CoachMode
from trainsync.modules.coach.packs import Key, Messages

__all__ = [
    "MAX_TOOL_CALLS",
    "TIMEOUT_S",
    "Asker",
    "Assistant",
    "DailyQuota",
    "RateLimiter",
    "RedisRateLimiter",
    "ToolError",
    "system_prompt",
]

log = get_logger(__name__)

MAX_TOOL_CALLS = 5
TIMEOUT_S = 20.0
MAX_RANGE_DAYS = 3660  # ten years

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _iso_date(value: object) -> object:
    """Only `YYYY-MM-DD` strings (pydantic alone would also take timestamps)."""
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        raise ValueError("must be a date as YYYY-MM-DD")
    return value


IsoDate = Annotated[date, BeforeValidator(_iso_date)]


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RangeArgs(_Args):
    start: IsoDate = Field(alias="from")
    end: IsoDate = Field(alias="to")
    sport_type: str | None = None

    @model_validator(mode="after")
    def _check_range(self) -> "RangeArgs":
        _check_dates(self.start, self.end)
        return self


class ListArgs(_Args):
    start: IsoDate | None = Field(default=None, alias="from")
    end: IsoDate | None = Field(default=None, alias="to")
    sport_type: str | None = None
    limit: int = Field(ge=1, le=MAX_LIST_LIMIT)

    @model_validator(mode="after")
    def _check_range(self) -> "ListArgs":
        if self.start is not None and self.end is not None:
            _check_dates(self.start, self.end)
        return self


class NoArgs(_Args):
    pass


def _check_dates(start: date, end: date) -> None:
    if end < start:
        raise ValueError("`to` is before `from`")
    if (end - start).days > MAX_RANGE_DAYS:
        raise ValueError(f"range longer than {MAX_RANGE_DAYS} days")


class ToolError(Exception):
    """Reported back to the model as an error tool result."""


class Assistant:
    def __init__(
        self,
        planner: Planner,
        read_api: ReadApi,
        limiter: RateLimiter,
        clock: Clock,
        msg: Messages,
        *,
        max_tool_calls: int = MAX_TOOL_CALLS,
        timeout_s: float = TIMEOUT_S,
        mode: CoachMode | None = None,
        profanity: BotProfanity = "roast",
        daily: DailyQuota | None = None,
    ) -> None:
        self._planner = planner
        self._api = read_api
        self._limiter = limiter
        self._clock = clock
        self._msg = msg
        # The effective intensity (savage unless soft mode); None = never savage.
        self._mode = mode
        self._daily = daily
        # BOT_PROFANITY; a chat's /swear choice (`using_profanity`) overrides it.
        self._profanity = profanity
        self._max_tool_calls = max_tool_calls
        self._timeout_s = timeout_s

    async def answer(self, chat_id: int, question: str, asker: Asker | None = None) -> str:
        if not await self._limiter.allow(chat_id):
            log.info("assistant_rate_limited", chat_id=chat_id)
            return self._msg(Key.ASSISTANT_RATE_LIMITED)
        if asker is not None and self._daily is not None and not await self._daily.allow(asker):
            log.info("assistant_daily_limit", user_id=asker.user_id)
            return self._msg(Key.ASSISTANT_RATE_LIMITED)
        try:
            async with asyncio.timeout(self._timeout_s):
                return await self._loop(question)
        except TimeoutError:
            log.warning("assistant_timeout", chat_id=chat_id)
            return self._msg(Key.ASSISTANT_TIMED_OUT)
        except anthropic.APIError as exc:
            log.warning("assistant_api_error", chat_id=chat_id, error=type(exc).__name__)
            return self._msg(Key.ASSISTANT_UNAVAILABLE)

    async def _loop(self, question: str) -> str:
        savage = self._mode is not None and await self._mode.savage()
        system = system_prompt(
            self._clock(),
            self._msg.tone,
            self._msg.lang,
            savage=savage,
            profanity=CURRENT_PROFANITY.get() or self._profanity,
        )
        messages: list[BetaMessageParam] = [{"role": "user", "content": question}]
        calls = 0
        over_limit = False
        while True:  # every round adds a tool call, and over the limit it ends: bounded
            response = await self._planner.create(system=system, tools=TOOLS, messages=messages)
            if response.stop_reason == "refusal":
                return self._msg(Key.ASSISTANT_REFUSED)
            tool_uses = [b for b in response.content if isinstance(b, BetaToolUseBlock)]
            if not tool_uses:
                return self._guarded(_text(response)) or self._msg(Key.ASSISTANT_UNAVAILABLE)
            if over_limit:
                return self._msg(
                    Key.ASSISTANT_TOO_MANY_CALLS
                )  # told to answer without tools, asked for more anyway
            messages.append({"role": "assistant", "content": response.content})
            results: list[BetaToolResultBlockParam] = []
            for tool_use in tool_uses:
                calls += 1
                if calls > self._max_tool_calls:
                    over_limit = True
                    results.append(_error(tool_use, "Tool call limit reached; answer now."))
                else:
                    results.append(await self._run(tool_use))
            messages.append({"role": "user", "content": results})

    def _guarded(self, reply: str) -> str:
        """A generated reply that breaks a guardrail (body shaming, slurs, food punishment) is
        never sent: the neutral fallback goes out instead (ADR 0030). Profanity passes."""
        broken = violations(reply, line=False)
        if broken:
            log.warning("assistant_reply_blocked", reasons=[v.value for v in broken])
            return self._msg(Key.ASSISTANT_UNAVAILABLE)
        return reply

    async def _run(self, tool_use: BetaToolUseBlock) -> BetaToolResultBlockParam:
        try:
            content = await self.execute(tool_use.name, tool_use.input)
        except ToolError as exc:
            log.info("assistant_tool_rejected", tool=tool_use.name, error=str(exc))
            return _error(tool_use, str(exc))
        log.info("assistant_tool_call", tool=tool_use.name)
        return {"type": "tool_result", "tool_use_id": tool_use.id, "content": content}

    async def execute(self, name: str, arguments: object) -> str:
        """Validate, then call the read API; the JSON result as a string."""
        try:
            if name in ("get_summary", "get_weekly"):
                args = RangeArgs.model_validate(arguments)
                if name == "get_summary":
                    summary = await self._api.summary(args.start, args.end, args.sport_type)
                    return summary.model_dump_json(by_alias=True)
                weekly = await self._api.weekly(args.start, args.end, args.sport_type)
                return weekly.model_dump_json(by_alias=True)
            if name == "list_activities":
                list_args = ListArgs.model_validate(arguments)
                page = await self._api.activities(
                    start=list_args.start,
                    end=list_args.end,
                    sport_type=list_args.sport_type,
                    limit=list_args.limit,
                )
                return page.model_dump_json(exclude={"next_cursor"})
            if name == "get_sync_status":
                NoArgs.model_validate(arguments)
                return (await self._api.sync_status()).model_dump_json()
        except ValidationError as exc:
            raise ToolError(f"Invalid arguments: {_errors(exc)}") from None
        except ReadApiError as exc:
            raise ToolError(f"The trainsync API failed: {exc}") from None
        raise ToolError(f"Unknown tool {name!r}")


def _text(response: BetaMessage) -> str:
    return "\n".join(b.text for b in response.content if b.type == "text").strip()


def _error(tool_use: BetaToolUseBlock, message: str) -> BetaToolResultBlockParam:
    return {"type": "tool_result", "tool_use_id": tool_use.id, "content": message, "is_error": True}


def _errors(exc: ValidationError) -> str:
    return json.dumps(
        [{"field": ".".join(map(str, e["loc"])) or "-", "error": e["msg"]} for e in exc.errors()]
    )
