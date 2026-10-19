"""Strava error responses → the exceptions callers handle (401, 404, other 4xx with Strava's
field errors). Pure mapping; the request itself is made in `client.py`."""

from http import HTTPStatus

import httpx

from trainsync.integrations.strava.errors import (
    StravaFieldError,
    StravaNotFound,
    StravaRequestError,
    StravaUnauthorized,
)


def client_error(response: httpx.Response) -> Exception:
    if response.status_code == HTTPStatus.UNAUTHORIZED:
        return StravaUnauthorized("strava rejected the access token")
    if response.status_code == HTTPStatus.NOT_FOUND:
        return StravaNotFound("strava object not found")
    message, errors = error_body(response)
    return StravaRequestError(response.status_code, message, errors)


def error_body(response: httpx.Response) -> tuple[str, tuple[StravaFieldError, ...]]:
    """Strava's `{"message": ..., "errors": [{"resource", "field", "code"}]}`, if that is what
    came back; anything else gives nothing."""
    try:
        body = response.json()
    except ValueError:
        return "", ()
    if not isinstance(body, dict):
        return "", ()
    raw = body.get("errors")
    items = raw if isinstance(raw, list) else []
    errors = tuple(
        StravaFieldError(
            resource=str(item.get("resource", "")),
            field=str(item.get("field", "")),
            code=str(item.get("code", "")),
        )
        for item in items
        if isinstance(item, dict)
    )
    return str(body.get("message", "")), errors
