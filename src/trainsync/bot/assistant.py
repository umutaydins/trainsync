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
from datetime import date, datetime
from typing import Annotated, Protocol

import anthropic
from anthropic.types.beta import (
    BetaMessage,
    BetaMessageParam,
    BetaToolParam,
    BetaToolResultBlockParam,
    BetaToolUseBlock,
)
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, model_validator
from redis.asyncio import Redis

from trainsync.bot.messages import Key, Messages
from trainsync.bot.read_api import ReadApi, ReadApiError
from trainsync.coach.guardrails import violations
from trainsync.coach.mode import CoachMode
from trainsync.core.clock import Clock
from trainsync.core.logging import get_logger
from trainsync.core.settings import BotLang, BotTone

log = get_logger(__name__)

MAX_TOOL_CALLS = 5
TIMEOUT_S = 20.0
MAX_TOKENS = 4096
MAX_RANGE_DAYS = 3660  # ten years
MAX_LIST_LIMIT = 50

SYSTEM_PROMPT = """\
You answer questions about one athlete's training, in a Telegram chat, using only the tools.

- Every number in your answer must come from a tool result in this conversation. Never estimate, \
recall or invent a value. If the tools can't answer the question, say so.
- Each result carries `last_synced_at`. If it is null, call get_sync_status before answering: \
with no athletes, say no Strava account is connected yet; with a backfill or incremental run \
`running` or `paused`, say the first sync is still in progress; only otherwise say there is no \
synced data. If it is more than a day before today, mention how old the data is.
- An empty result means no activities in that range: say so, don't guess.
- Metric units: km with one decimal (convert from metres), hours and minutes, metres of \
elevation, pace in min/km for runs.
- Dates are UTC calendar days; ranges are inclusive. A month is its first to its last day.
- Plain text, no Markdown, at most a few short lines.
- {language}

{guardrails}

{persona}

Today is {today} ({weekday}).
"""

# Hard limits in every tone and intensity (ADR 0030); the code enforces them too.
GUARDRAILS = (
    "Hard limits, whatever the tone: never comment on the athlete's body, weight or appearance; "
    "no slurs about ethnicity, religion, sexual orientation, disability, gender or similar; if "
    "the athlete mentions pain, injury, illness, dizziness, chest pain or the like, drop any "
    "push or roast and tell them to rest and, if it is serious or persists, see a doctor; never "
    "push eating below their nutrition target and never suggest 'burning off' food or exercise "
    "as punishment for eating. Food: eat it, log it, stay in the daily target."
)
# BOT_INTENSITY=savage (ADR 0030): the owner's explicit opt-in.
SAVAGE = (
    "Intensity: SAVAGE. The user explicitly asked for this tone and set it himself: you are his "
    'brutal coach ("Koç"). Profanity has no limit: swear as hard as you like in Turkish. Roast '
    "excuses, skipped workouts and weak effort without mercy, compared with his program and "
    "history from the tools, then always give one concrete action for today. Keep it short. You "
    "may end with a short, original English punchline (cold, quotable, never a quote of a real "
    "person). The hard limits above still apply and override this paragraph."
)

# BOT_TONE / BOT_LANG (ADR 0016). The persona changes the wording, never the numbers.
PERSONAS: dict[BotTone, str] = {
    "neutral": "Tone: friendly, factual and brief.",
    "hardcore": (
        'Tone: you are Coach ("Koç" in Turkish), an original tough-love running coach. Short, '
        "blunt sentences. Mild profanity is allowed, and only these words: damn, hell, crap in "
        "English; lan, ulan, hassiktir in Turkish. Use it sparingly. Judge only effort and "
        "consistency: never comment on the athlete's body, weight, appearance or identity, and "
        "never insult them. Do not name, quote or imitate any real person. If this week's "
        "training time is under half of last week's, push hard; at or above last week's, "
        "acknowledge it, then raise the bar. If the last two weeks are both empty, ask whether "
        "it is injury or rest instead of pushing. The rules above still hold: every number "
        "comes from a tool result."
    ),
}
LANGUAGES: dict[BotLang, str] = {
    "en": "Reply in English.",
    "tr": "Reply in Turkish.",
}

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


def _nullable(kind: str, description: str) -> dict[str, object]:
    return {"type": [kind, "null"], "description": description}


_DATE = {"type": "string", "description": "UTC day, YYYY-MM-DD"}
_SPORT = _nullable("string", "Strava sport_type such as Run, Ride, Swim; null for all sports")
_RANGE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "from": {**_DATE, "description": "First day, YYYY-MM-DD (inclusive)"},
        "to": {**_DATE, "description": "Last day, YYYY-MM-DD (inclusive)"},
        "sport_type": _SPORT,
    },
    "required": ["from", "to", "sport_type"],
    "additionalProperties": False,
}

TOOLS: list[BetaToolParam] = [
    {
        "name": "get_summary",
        "description": (
            "Totals for a date range: count, distance_m, moving_time_s, elevation_gain_m, the "
            "same per sport_type, and the longest activity. Use for 'how much / how far / how "
            "many' questions over a period."
        ),
        "input_schema": _RANGE_SCHEMA,
        "strict": True,
    },
    {
        "name": "get_weekly",
        "description": (
            "Per ISO week (Monday start) totals for a date range, zero-filled. Use for trends, "
            "best or worst week, week-by-week comparisons."
        ),
        "input_schema": _RANGE_SCHEMA,
        "strict": True,
    },
    {
        "name": "list_activities",
        "description": (
            "Individual activities, newest first: name, sport_type, start_date, distance_m, "
            "moving_time_s, elevation_gain_m, average_heartrate. Use for questions about "
            "specific workouts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "from": _nullable("string", "First day, YYYY-MM-DD, or null"),
                "to": _nullable("string", "Day after the last one, YYYY-MM-DD, or null"),
                "sport_type": _SPORT,
                "limit": {"type": "integer", "description": f"1 to {MAX_LIST_LIMIT}"},
            },
            "required": ["from", "to", "sport_type", "limit"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "get_sync_status",
        "description": "How fresh the data is and whether syncing with Strava is healthy.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "strict": True,
    },
]


class Planner(Protocol):
    """One Messages API turn. The real one is `AnthropicPlanner`; tests script a fake."""

    async def create(
        self, *, system: str, tools: list[BetaToolParam], messages: list[BetaMessageParam]
    ) -> BetaMessage: ...


class AnthropicPlanner:
    def __init__(self, client: anthropic.AsyncAnthropic, model: str) -> None:
        self._client = client
        self._model = model

    async def create(
        self, *, system: str, tools: list[BetaToolParam], messages: list[BetaMessageParam]
    ) -> BetaMessage:
        return await self._client.beta.messages.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=tools,
            messages=messages,
            # Short factual answers from tool results: low effort is plenty.
            output_config={"effort": "low"},
            # On a safety decline, let the API re-run the turn on its recommended fallback.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )


class RateLimiter(Protocol):
    async def allow(self, chat_id: int) -> bool: ...


class RedisRateLimiter:
    """Fixed one-hour windows per chat: `INCR` a key that expires with its window."""

    def __init__(self, redis: Redis, limit_per_hour: int, clock: Clock) -> None:
        self._redis = redis
        self._limit = limit_per_hour
        self._clock = clock

    async def allow(self, chat_id: int) -> bool:
        window = int(self._clock().timestamp()) // 3600
        key = f"assistant:quota:{chat_id}:{window}"
        count = int(await self._redis.incr(key))
        if count == 1:
            await self._redis.expire(key, 3600)
        return count <= self._limit


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
    ) -> None:
        self._planner = planner
        self._api = read_api
        self._limiter = limiter
        self._clock = clock
        self._msg = msg
        # The effective intensity (savage unless soft mode); None = never savage.
        self._mode = mode
        self._max_tool_calls = max_tool_calls
        self._timeout_s = timeout_s

    async def answer(self, chat_id: int, question: str) -> str:
        if not await self._limiter.allow(chat_id):
            log.info("assistant_rate_limited", chat_id=chat_id)
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
        system = system_prompt(self._clock(), self._msg.tone, self._msg.lang, savage=savage)
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


def system_prompt(
    now: datetime, tone: BotTone = "neutral", lang: BotLang = "en", *, savage: bool = False
) -> str:
    today = now.date()
    persona = f"{PERSONAS[tone]}\n\n{SAVAGE}" if savage else PERSONAS[tone]
    return SYSTEM_PROMPT.format(
        today=today.isoformat(),
        weekday=today.strftime("%A"),
        language=LANGUAGES[lang],
        persona=persona,
        guardrails=GUARDRAILS,
    )


def _text(response: BetaMessage) -> str:
    return "\n".join(b.text for b in response.content if b.type == "text").strip()


def _error(tool_use: BetaToolUseBlock, message: str) -> BetaToolResultBlockParam:
    return {"type": "tool_result", "tool_use_id": tool_use.id, "content": message, "is_error": True}


def _errors(exc: ValidationError) -> str:
    return json.dumps(
        [{"field": ".".join(map(str, e["loc"])) or "-", "error": e["msg"]} for e in exc.errors()]
    )
