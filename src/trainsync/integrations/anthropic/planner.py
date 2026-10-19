"""One Claude Messages API turn for the assistant (ADR 0014)."""

from typing import Protocol

import anthropic
from anthropic.types.beta import BetaMessage, BetaMessageParam, BetaToolParam

MAX_TOKENS = 4096


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
