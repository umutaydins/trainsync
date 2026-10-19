"""Check-in keyboards: the five status buttons and each step's buttons."""

from datetime import date
from decimal import Decimal

from trainsync.integrations.telegram.client import Button, Keyboard
from trainsync.modules.chat.checkin.state import (
    ENERGY_LEVELS,
    STATUS_BUTTONS,
    STATUS_CODES,
    FlowState,
    callback,
)
from trainsync.modules.chat.common import Reply, kg
from trainsync.modules.coach.packs import Key, Messages, NeutralKey

STEP_KG = Decimal("2.5")
MINUS = chr(0x2212)  # the minus sign, for the "-2.5 kg" button


def status_keyboard(msg: Messages, day: date, seq: int) -> Keyboard:
    def button(code: str) -> Button:
        return Button(msg(STATUS_BUTTONS[STATUS_CODES[code]]), callback(day, seq, f"s:{code}"))

    return (
        (button("done"), button("partial"), button("skipped")),
        (button("rest"), button("sick")),
    )


def prompt(msg: Messages, day: date, *, reminder: bool = False) -> Reply:
    """The evening question with the five status buttons (the worker sends it with seq 0)."""
    text = msg(Key.CHECKIN_REMINDER if reminder else Key.CHECKIN_PROMPT)
    return Reply(text, status_keyboard(msg, day, 0))


def step_keyboard(msg: Messages, day: date, state: FlowState) -> Keyboard | None:
    seq = state.seq

    def button(text: str, action: str) -> Button:
        return Button(text, callback(day, seq, action))

    skip = button(msg.neutral(NeutralKey.BUTTON_SKIP), "k")
    if state.step == "exercise":
        current = state.planned[state.index]
        rows: list[tuple[Button, ...]] = []
        if current.weight_kg is not None:
            plus = msg(Key.CHECKIN_BTN_STEP, step=f"+{kg(STEP_KG)}")
            minus = msg(Key.CHECKIN_BTN_STEP, step=f"{MINUS}{kg(STEP_KG)}")
            rows.append((button(msg(Key.CHECKIN_BTN_AS_PLANNED), "p"),))
            rows.append((button(plus, "+"), button(minus, "-")))
        rows.append((button(msg(Key.CHECKIN_BTN_SKIP_EXERCISE), "x"),))
        return tuple(rows)
    if state.step == "freeform":
        return ((button(msg(Key.CHECKIN_BTN_FINISH), "f"),),)
    if state.step in {"reason", "scale", "sleep"}:
        return ((skip,),)
    if state.step == "energy":
        return (tuple(button(str(n), f"e:{n}") for n in ENERGY_LEVELS), (skip,))
    if state.step == "done":
        return ((button(msg(Key.CHECKIN_BTN_EDIT), "edit"),),)
    return None
