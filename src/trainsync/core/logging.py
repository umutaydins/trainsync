"""structlog configuration: JSON in prod/test, console in dev, secrets redacted."""

import logging
import re
from collections.abc import Mapping
from typing import cast

import structlog
from structlog.typing import EventDict, FilteringBoundLogger, Processor, WrappedLogger

from trainsync.core.settings import Settings

REDACTED = "***"
_SENSITIVE_KEY = re.compile(r"token|secret|authorization|password|api_key", re.IGNORECASE)


def _redact_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {k: REDACTED if _is_sensitive(k) else _redact_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact_value(v) for v in value]
    return value


def _is_sensitive(key: object) -> bool:
    return isinstance(key, str) and _SENSITIVE_KEY.search(key) is not None


def redact_secrets(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Replace values of sensitive-looking keys (recursively) with `***`."""
    for key in list(event_dict):
        if key == "event":
            continue
        event_dict[key] = REDACTED if _is_sensitive(key) else _redact_value(event_dict[key])
    return event_dict


def shared_processors() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_secrets,
    ]


def configure_logging(settings: Settings) -> None:
    level = logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)
    renderer: Processor = (
        structlog.dev.ConsoleRenderer()
        if settings.env == "dev"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            *shared_processors(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> FilteringBoundLogger:
    return cast(FilteringBoundLogger, structlog.get_logger(name))


def warn_dev_secrets(settings: Settings, logger: FilteringBoundLogger) -> list[str]:
    """With ENV=prod, warn about secrets still at a docker-compose dev default. Logs the
    variable names only (under `variables`, which the redaction leaves readable)."""
    if settings.env != "prod":
        return []
    names = settings.dev_secrets_in_use()
    if names:
        logger.warning(
            "dev_default_secrets_in_prod",
            variables=names,
            hint="set your own values in .env; the docker-compose defaults are DEV-ONLY",
        )
    return names
