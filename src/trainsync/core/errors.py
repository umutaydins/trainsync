"""Documented error responses: every error in the OpenAPI spec carries an example body."""

from typing import Any

Responses = dict[int | str, dict[str, Any]]


def error(description: str, detail: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"example": {"detail": detail}}},
    }


UNAUTHORIZED: Responses = {
    401: error(
        "Not signed in: no valid session token (`Authorization: Bearer`) or `X-API-Key`",
        "sign in or send a valid API key",
    )
}
FORBIDDEN_OWNER: Responses = {403: error("Owner only", "owner only")}

VALIDATION_ERROR_EXAMPLE: dict[str, Any] = {
    "detail": [
        {
            "type": "less_than_equal",
            "loc": ["query", "limit"],
            "msg": "Input should be less than or equal to 200",
            "input": "500",
        }
    ]
}
