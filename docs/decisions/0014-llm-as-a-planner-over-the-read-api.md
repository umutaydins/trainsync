# 0014 — LLM as a planner over the read API, never as a data source

- Status: accepted
- Date: 2026-10-18

## Context
"How many km did I run in September compared to August?" is easy to ask and awkward to map to
fixed commands. A language model can map it, but a model asked about numbers will happily
produce plausible ones. The bot is single-user, so cost and abuse are small but real, and the
answer must be correct, not merely fluent.

## Decision
Claude (Anthropic Python SDK, `ASSISTANT_MODEL`, default `claude-sonnet-5-5` at low effort) is
used only to decide **which read-API calls to make** and to phrase the answer.
- Four tools, mapped 1:1 to read endpoints: `get_summary`, `get_weekly`, `list_activities`,
  `get_sync_status`. Strict JSON schemas (`strict: true`, no extra properties); on our side every
  call is validated again (ISO dates only, `to` ≥ `from`, at most ten years, `limit` ≤ 50, no
  unknown tools). Invalid calls are returned to the model as `is_error` tool results and never
  executed.
- Tools call the same HTTP API as every client, with the bot's API key. The model never sees the
  database and has no write path.
- The system prompt says: every number from a tool result, say when data is missing, mention
  `last_synced_at` when it is over a day old, metric units, the user's language.
- Guards: at most 5 tool calls and 20 s per question, 20 questions per chat per hour (Redis
  fixed window), only allowlisted chats (the bot's allowlist applies first). Commands stay
  deterministic and never go through the model.
- A hand-written loop rather than the SDK's beta tool runner, because the call limit, the
  validation-before-execution and the overall timeout are exactly the parts we need to own.
- Server-side refusal fallback (`fallbacks: "default"`) is enabled; a remaining refusal gets a
  fixed reply.
- Off unless `ANTHROPIC_API_KEY` is set. Tests use a scripted fake planner; no test can reach
  Anthropic (the test suite points the SDK at an unroutable base URL).

## Alternatives considered
- **Let the model answer from a data dump** (e.g. a month of activities in the prompt): cheaper
  to build, but the arithmetic is the model's, and nothing stops a made-up number.
- **Text-to-SQL**: maximal flexibility, but gives a model a query path into the database; the
  read API already encodes the aggregations we trust (and tests).
- **No LLM, more commands**: still the fallback; every command works without the assistant.

## Consequences
- An answer can only be as good as the four endpoints; questions they cannot answer get "I can't
  tell" rather than a guess.
- The Anthropic SDK brings its own HTTP client (httpx2) next to the process's httpx client;
  it is created once in the bot's lifespan and closed on shutdown.
- Cost per question is a few small requests; the hourly limit caps it.
