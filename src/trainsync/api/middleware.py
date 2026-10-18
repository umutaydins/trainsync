"""ASGI middleware: request id assignment, log correlation, request latency metrics and the
read-only demo guard."""

import json
import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from trainsync.core.metrics import HTTP_REQUEST_DURATION

REQUEST_ID_HEADER = "x-request-id"
_MAX_REQUEST_ID_LEN = 128


class RequestIdMiddleware:
    """Use the incoming `X-Request-ID` (or a new uuid4), bind it to the log context, echo it."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        with structlog.contextvars.bound_contextvars(request_id=request_id):
            await self.app(scope, receive, send_with_header)


class MetricsMiddleware:
    """`http_request_duration_seconds{route}` labelled with the route *template* (e.g.
    `/v1/activities`), never the raw path, so the label set stays small."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        try:
            await self.app(scope, receive, send)
        finally:
            route = scope.get("route")
            template = getattr(route, "path", None) or "unmatched"
            HTTP_REQUEST_DURATION.labels(template).observe(time.perf_counter() - started)


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == REQUEST_ID_HEADER.encode():
            decoded: str = value.decode("latin-1").strip()
            if decoded and len(decoded) <= _MAX_REQUEST_ID_LEN and decoded.isprintable():
                return decoded
    return None


DEMO_DETAIL = "This is a read-only demo."
# Lets a client (the web BFF) tell this 403 from an authorization failure.
DEMO_HEADER = "x-trainsync-demo"
READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# GET routes that still write: the OAuth callback stores tokens; login only starts that flow.
WRITE_PATH_PREFIXES = ("/auth/strava/",)


def is_demo_blocked(method: str, path: str) -> bool:
    """A request the read-only demo refuses: any non-read method, or the Strava connect flow."""
    return method.upper() not in READ_METHODS or path.startswith(WRITE_PATH_PREFIXES)


class DemoReadOnlyMiddleware:
    """`DEMO_MODE=true` (P7.9, ADR 0028): answer every write with 403 before any route runs, so a
    new write route is covered without touching it. The demo data is seeded by `trainsync.demo`
    straight into the database, never over HTTP."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_demo_blocked(scope["method"], scope["path"]):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"detail": DEMO_DETAIL}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (DEMO_HEADER.encode(), b"read-only"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
