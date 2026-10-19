"""Links the owner hands out: the invite and the password reset (no email yet, ADR 0034)."""

from urllib.parse import urlencode

from trainsync.core.settings import Settings
from trainsync.modules.auth.constants import (
    INVITE_QUERY,
    REGISTER_PATH,
    RESET_PATH,
    RESET_QUERY,
)


def _link(settings: Settings, path: str, query: dict[str, str]) -> str:
    base = settings.dashboard_public_url.rstrip("/")
    return f"{base}{path}?{urlencode(query)}"


def invite_link(settings: Settings, code: str) -> str:
    return _link(settings, REGISTER_PATH, {INVITE_QUERY: code})


def reset_link(settings: Settings, token: str) -> str:
    return _link(settings, RESET_PATH, {RESET_QUERY: token})
