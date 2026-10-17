"""ASGI middleware: request id assignment, log correlation and request latency metrics."""

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
