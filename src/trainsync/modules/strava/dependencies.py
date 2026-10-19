"""FastAPI dependency for the process's shared `StravaClient`."""

from typing import Annotated

from fastapi import Depends, Request

from trainsync.integrations.strava.client import StravaClient


def get_strava_client(request: Request) -> StravaClient:
    client: StravaClient = request.app.state.strava
    return client


StravaDep = Annotated[StravaClient, Depends(get_strava_client)]
