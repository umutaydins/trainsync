"""arq worker entry point: `arq trainsync.worker.WorkerSettings`."""

import os
from typing import Any, ClassVar

from arq.connections import RedisSettings

from trainsync.core.settings import Settings

_DEFAULT_REDIS_URL: str = Settings.model_fields["redis_url"].default


async def ping(ctx: dict[str, Any]) -> str:
    return "pong"


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ping]
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", _DEFAULT_REDIS_URL))
