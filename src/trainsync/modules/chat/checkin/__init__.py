"""The daily check-in conversation (P6.9, ADR 0020): a small finite-state machine.

    status ─┬─ done/partly + program ─→ exercise (one per planned exercise) ─┐
            ├─ done/partly, no program → freeform (`bench 80x5x3` lines, Finish) ┤
            ├─ skipped ─→ reason ─────────────────────────────────────────────┤
            └─ rest / sick ───────────────────────────────────────────────────┤
                                     scale → sleep → energy → done (summary + Edit)

State lives in Redis (`checkin:{chat}:{yyyymmdd}`, 6 h TTL), so the bot can restart mid-flow.
Every button carries `ci:{yyyymmdd}:{seq}:{action}`; `seq` goes up on every step, so a button
from an older message (or a double tap, or a redelivered press) no longer matches and is answered
with a polite "that button is from an earlier question". A text answer redelivered by Telegram
has an `update_id` the state has already seen and is ignored.

Writes are idempotent: the workout is started with `uuid5("checkin:{date}:workout")`, sets use
`uuid5("checkin:{date}:{exercise_id}:{set_index}")` and the check-in itself is
`PUT /v1/checkins/{date}`, so "edit" and retries overwrite instead of adding.
"""

from trainsync.modules.chat.checkin.flow import CheckinFlow
from trainsync.modules.chat.checkin.keyboards import MINUS, STEP_KG, prompt, status_keyboard
from trainsync.modules.chat.checkin.state import (
    STATE_TTL_S,
    FlowState,
    callback,
    set_id,
    state_key,
    workout_client_id,
)

__all__ = [
    "MINUS",
    "STATE_TTL_S",
    "STEP_KG",
    "CheckinFlow",
    "FlowState",
    "callback",
    "prompt",
    "set_id",
    "state_key",
    "status_keyboard",
    "workout_client_id",
]
