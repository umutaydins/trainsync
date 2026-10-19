import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from trainsync.core.crypto import InvalidEncryptionKeyError, TokenCipher, TokenDecryptError
from trainsync.core.settings import Settings

PLAIN = "access-token-plaintext-123"


def _key() -> str:
    return Fernet.generate_key().decode()


def test_round_trip_and_ciphertext_is_randomised() -> None:
    cipher = TokenCipher(SecretStr(_key()))
    first, second = cipher.encrypt(PLAIN), cipher.encrypt(PLAIN)
    assert first != second
    assert PLAIN.encode() not in first
    assert cipher.decrypt(first) == PLAIN
    assert cipher.decrypt(second) == PLAIN


def test_from_settings(settings: Settings) -> None:
    cipher = TokenCipher.from_settings(settings)
    assert cipher.decrypt(cipher.encrypt(PLAIN)) == PLAIN


def test_old_key_still_decrypts_after_rotation() -> None:
    old, new = _key(), _key()
    old_ciphertext = TokenCipher(SecretStr(old)).encrypt(PLAIN)
    rotated = TokenCipher(SecretStr(f"{new}, {old}"))
    assert rotated.decrypt(old_ciphertext) == PLAIN
    # New encryptions use the first (new) key only.
    assert TokenCipher(SecretStr(new)).decrypt(rotated.encrypt(PLAIN)) == PLAIN


def test_unknown_key_raises_without_echoing_data() -> None:
    ciphertext = TokenCipher(SecretStr(_key())).encrypt(PLAIN)
    other_key = _key()
    with pytest.raises(TokenDecryptError) as exc_info:
        TokenCipher(SecretStr(other_key)).decrypt(ciphertext)
    message = str(exc_info.value)
    assert PLAIN not in message
    assert ciphertext.decode() not in message
    assert other_key not in message


def test_tampered_ciphertext_raises() -> None:
    cipher = TokenCipher(SecretStr(_key()))
    ciphertext = bytearray(cipher.encrypt(PLAIN))
    ciphertext[20] = ord("A") if ciphertext[20] != ord("A") else ord("B")
    with pytest.raises(TokenDecryptError) as exc_info:
        cipher.decrypt(bytes(ciphertext))
    assert PLAIN not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


@pytest.mark.parametrize("bad", ["", " , ", "not-a-fernet-key-but-a-secret"])
def test_malformed_key_is_a_clear_error_without_echo(bad: str) -> None:
    with pytest.raises(InvalidEncryptionKeyError) as exc_info:
        TokenCipher(SecretStr(bad))
    if bad.strip(" ,"):
        assert bad not in str(exc_info.value)
