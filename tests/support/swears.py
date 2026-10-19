"""Is there a swear word in a text? For the profanity tests (ADR 0032): max must swear, calm
replies and roast-mode confirmations must not."""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

import re

SWEAR = re.compile(
    r"\b(?:"
    # Turkish
    r"amk|amına|siktir\w*|sik(?:eyim|tin|ik)\w*|lan|ulan|hassiktir|bok\w*|göt\w*"
    # English
    r"|fuck\w*|motherfuck\w*|shit\w*|bullshit|damn\w*|goddamn\w*|hell|ass|asses|half-assed"
    r"|weak-ass|crap\w*|piss\w*"
    r")\b",
    re.IGNORECASE,
)


def swears(text: str) -> bool:
    return SWEAR.search(text) is not None
