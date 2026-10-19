"""Disconnecting Strava (ADR 0037): revoke the app at Strava, then drop the athlete's tokens
and activities.

The API marks the athlete inactive at once (no sync touches it any more) and enqueues
`strava_disconnect`. Strava's deauthorize call is best effort: a failure is logged and the local
cleanup still happens, so the user is never left half-connected.
"""

from typing import Any, Protocol

from arq.worker import func

from trainsync.core.logging import get_logger
from trainsync.integrations.strava.errors import StravaError
from trainsync.modules.sync.context import job_log_context, worker_context
from trainsync.modules.sync.deauthorization import deauthorize

log = get_logger(__name__)


class Deauthorizer(Protocol):
    async def deauthorize(self, athlete_id: int) -> None: ...


async def revoke_at_strava(strava: Deauthorizer, athlete_id: int) -> bool:
    try:
        await strava.deauthorize(athlete_id)
    except (StravaError, LookupError, RuntimeError) as exc:
        log.warning("strava_deauthorize_failed", athlete_id=athlete_id, error=type(exc).__name__)
        return False
    return True


async def strava_disconnect(ctx: dict[str, Any], athlete_id: int) -> str:
    with job_log_context(ctx, "strava_disconnect", athlete_id=athlete_id):
        wc = worker_context(ctx)
        revoked = await revoke_at_strava(wc.strava, athlete_id)
        async with wc.sessionmaker.begin() as session:
            removed = await deauthorize(session, athlete_id)
        log.info("strava_disconnected", athlete_id=athlete_id, revoked=revoked, removed=removed)
        return "revoked" if revoked else "local_only"


strava_disconnect_job = func(strava_disconnect, name="strava_disconnect", max_tries=3)
