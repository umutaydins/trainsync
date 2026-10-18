"""Parsers for what the owner types: sets (`80x5x3`, `80x5,5,4`, `bw x12x3`), `/log`, `/eat`
and plain numbers. Shared by the `/log` command (P6.8) and the daily check-in (P6.9)."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MAX_WEIGHT_KG = Decimal(500)
WEIGHT_STEP_KG = Decimal("0.25")  # what the API accepts (ADR 0017)
MAX_REPS = 100
MAX_SETS = 20
MAX_GRAMS = Decimal(5000)

# <weight or bw> x <reps[,reps…]> [x <sets>]; spaces are ignored, and the multiplication sign
# or `*` work as the `x`.
_SETS = re.compile(r"^(bw|\d{1,3}(?:\.\d{1,2})?)x(\d{1,3}(?:,\d{1,3})*)(?:x(\d{1,2}))?$")


@dataclass(frozen=True, slots=True)
class ParsedSet:
    weight_kg: Decimal  # 0 = bodyweight
    reps: int


class ParseError(ValueError):
    """The text is not in the expected format."""


def parse_sets(text: str) -> list[ParsedSet]:
    """`80x5x3` → three sets of 5 at 80 kg; `80x5,5,4` → sets of 5, 5, 4; `bw x12x3` → three
    bodyweight sets of 12 (0 kg); `80x5` → one set. Raises `ParseError`."""
    compact = re.sub(r"\s+", "", text.lower()).replace("\u00d7", "x").replace("*", "x")
    match = _SETS.match(compact)
    if match is None:
        raise ParseError(text)
    weight_text, reps_text, sets_text = match.groups()
    weight = Decimal(0) if weight_text == "bw" else Decimal(weight_text)
    if weight > MAX_WEIGHT_KG or weight % WEIGHT_STEP_KG != 0:
        raise ParseError(text)
    reps = [int(r) for r in reps_text.split(",")]
    if sets_text is not None:
        if len(reps) > 1:
            raise ParseError(text)  # `80x5,5x3` is ambiguous
        reps = reps * int(sets_text)
    if not 1 <= len(reps) <= MAX_SETS or not all(1 <= r <= MAX_REPS for r in reps):
        raise ParseError(text)
    return [ParsedSet(weight, r) for r in reps]


def parse_log(args: list[str]) -> tuple[str, list[ParsedSet]]:
    """`/log bench press 80x5x3` → ("bench press", sets). The set spec is the longest tail of
    up to five words that parses (`bw x12x3`, `80 x 5 x 3`); the words before it name the
    exercise."""
    for words in range(min(5, len(args) - 1), 0, -1):
        try:
            sets = parse_sets(" ".join(args[-words:]))
        except ParseError:
            continue
        return " ".join(args[:-words]), sets
    raise ParseError(" ".join(args))


def parse_eat(args: list[str]) -> tuple[str, Decimal]:
    """`/eat greek yogurt 150` (or `150g`, `150 g`) → ("greek yogurt", 150)."""
    words = list(args)
    if words and words[-1].lower() == "g":
        words.pop()
    if len(words) < 2:
        raise ParseError(" ".join(args))
    amount = words[-1].lower().removesuffix("g")
    grams = parse_number(amount)
    if grams is None or not 0 < grams <= MAX_GRAMS:
        raise ParseError(" ".join(args))
    return " ".join(words[:-1]), grams


def parse_number(text: str) -> Decimal | None:
    """`78.4` or `78,4` → Decimal; None when it is not a plain number."""
    cleaned = text.strip().replace(",", ".")
    if not re.fullmatch(r"\d{1,4}(?:\.\d{1,2})?", cleaned):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:  # pragma: no cover - the regex already guarantees a number
        return None


def parse_choice(text: str, count: int) -> int | None:
    """A reply to a numbered list: `2` → index 1. None when it is not a number at all;
    raises `ParseError` for a number outside 1..count."""
    cleaned = text.strip().rstrip(".)")
    if not cleaned.isdigit():
        return None
    number = int(cleaned)
    if not 1 <= number <= count:
        raise ParseError(text)
    return number - 1
