"""Encryption helpers. OAuth tokens are never stored in plaintext."""
from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings


class SecretKeyMissing(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().secret_key
    if not key:
        raise SecretKeyMissing(
            "SECRET_KEY is not set. Generate one with: "
            "python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    return Fernet(key.encode())


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    try:
        return _fernet().decrypt(token)
    except InvalidToken as exc:
        raise ValueError("Cannot decrypt secret: wrong SECRET_KEY or corrupted data") from exc


class EncryptedJSON(TypeDecorator):
    """Stores a JSON-serialisable value encrypted with Fernet (AES-128-CBC + HMAC)."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> bytes | None:  # noqa: ANN001
        if value is None:
            return None
        return encrypt_bytes(json.dumps(value).encode("utf-8"))

    def process_result_value(self, value: bytes | None, dialect) -> Any:  # noqa: ANN001
        if value is None:
            return None
        return json.loads(decrypt_bytes(bytes(value)).decode("utf-8"))
