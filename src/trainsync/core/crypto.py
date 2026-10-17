"""Encryption of OAuth tokens at rest (Fernet, with key rotation via MultiFernet)."""

from typing import Self

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from pydantic import SecretStr

from trainsync.core.settings import Settings


class TokenDecryptError(Exception):
    """Ciphertext could not be decrypted with any configured key."""


class InvalidEncryptionKeyError(ValueError):
    """`TOKEN_ENCRYPTION_KEY` is empty or contains a malformed Fernet key."""


class TokenCipher:
    """Encrypts with the first key; decrypts with any of the comma-separated keys."""

    def __init__(self, keys: SecretStr) -> None:
        parts = [part.strip() for part in keys.get_secret_value().split(",") if part.strip()]
        if not parts:
            raise InvalidEncryptionKeyError("TOKEN_ENCRYPTION_KEY is empty")
        fernets: list[Fernet] = []
        for index, part in enumerate(parts):
            try:
                fernets.append(Fernet(part))
            except (ValueError, TypeError):
                raise InvalidEncryptionKeyError(
                    f"TOKEN_ENCRYPTION_KEY entry #{index + 1} is not a valid Fernet key"
                ) from None
        self._fernet = MultiFernet(fernets)

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(settings.token_encryption_key)

    def encrypt(self, plain: str) -> bytes:
        return self._fernet.encrypt(plain.encode())

    def decrypt(self, cipher: bytes) -> str:
        try:
            return self._fernet.decrypt(cipher).decode()
        except InvalidToken:
            raise TokenDecryptError(
                "token ciphertext is invalid or was encrypted with an unknown key"
            ) from None
