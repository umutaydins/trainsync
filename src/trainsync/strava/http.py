"""The shared outbound `httpx.AsyncClient` (one per process)."""

import httpx

from trainsync.core.settings import Settings

TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=10.0, pool=5.0)
LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)


def build_http_client(settings: Settings) -> httpx.AsyncClient:
    del settings  # reserved: per-environment tuning; base URLs are applied per request
    return httpx.AsyncClient(
        timeout=TIMEOUT,
        limits=LIMITS,
        headers={"User-Agent": "trainsync"},
        follow_redirects=False,
    )
