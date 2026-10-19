"""Auth failures with the HTTP status the routers answer with. Messages are generic on purpose:
a failed login never says whether the email exists."""

from fastapi import status


class AuthError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, detail: str, *, retry_after: int | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.retry_after = retry_after


class InvalidCredentialsError(AuthError):
    status_code = status.HTTP_401_UNAUTHORIZED


class RateLimitedError(AuthError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS


class RegistrationClosedError(AuthError):
    status_code = status.HTTP_403_FORBIDDEN


class EmailTakenError(AuthError):
    status_code = status.HTTP_409_CONFLICT


class InvalidTokenError(AuthError):
    """An invite or reset token that is unknown, used, revoked or expired."""

    status_code = status.HTTP_400_BAD_REQUEST


class WeakPasswordError(AuthError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
