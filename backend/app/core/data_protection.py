"""Application-level authenticated encryption for non-searchable sensitive fields."""

from __future__ import annotations

import base64
import hashlib
from datetime import date, datetime
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import Text, TypeDecorator

from app.core.config import settings

_ENVELOPE_PREFIX = "fpenc:v1:"


class DataProtectionError(ValueError):
    """Raised when encrypted data cannot be safely read or written."""


def _fernet_key() -> bytes:
    """Use a dedicated production key; derive a stable dev/test key otherwise."""
    configured = getattr(settings, "DATA_PROTECTION_KEY", "")
    if configured:
        key = configured.encode("ascii")
        try:
            Fernet(key)
        except (ValueError, TypeError) as exc:
            raise DataProtectionError("DATA_PROTECTION_KEY is invalid") from exc
        return key

    if getattr(settings, "ENVIRONMENT", "development") == "production":
        raise DataProtectionError(
            "DATA_PROTECTION_KEY must be configured in production"
        )
    secret = getattr(settings, "SECRET_KEY", "")
    if not secret:
        raise DataProtectionError(
            "SECRET_KEY is required to derive a test/development key"
        )
    raw = hashlib.sha256((secret + ":finpilot-data-protection-v1").encode()).digest()
    return base64.urlsafe_b64encode(raw)


@lru_cache(maxsize=4)
def _cipher_for_key(key: bytes) -> Fernet:
    return Fernet(key)


def _cipher() -> Fernet:
    return _cipher_for_key(_fernet_key())


class DataProtectionCipher:
    """Convenient API for field encryption and integrity-protected decryption."""

    def encrypt(self, value: str) -> str:
        if not isinstance(value, str):
            raise TypeError("Only strings can be encrypted")
        return _ENVELOPE_PREFIX + _cipher().encrypt(value.encode("utf-8")).decode(
            "ascii"
        )

    def decrypt(self, value: str) -> str:
        if not value.startswith(_ENVELOPE_PREFIX):
            # Transitional compatibility: historical plaintext is read during backfill.
            return value
        token = value[len(_ENVELOPE_PREFIX) :]
        try:
            return _cipher().decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
            # Never return damaged ciphertext as if it were plaintext.
            raise DataProtectionError("Unable to decrypt protected data") from exc

    def is_encrypted(self, value: str | None) -> bool:
        return bool(value and value.startswith(_ENVELOPE_PREFIX))

    def fingerprint(self, value: str) -> str:
        """Non-reversible SHA-256 digest; do not use it for low-entropy secrets."""
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


class EncryptedString(TypeDecorator[str]):
    """Transparent authenticated encryption for string columns.

    SQL queries that compare/search encrypted values do not work as they did on
    plaintext. Apply this only to fields that are not used for SQL filtering,
    grouping, uniqueness, or lexical sorting.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return DataProtectionCipher().encrypt(value)

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return DataProtectionCipher().decrypt(value)


class EncryptedDate(TypeDecorator[date]):
    """Stores a date as an encrypted ISO-8601 string, returning ``date`` values."""

    impl = Text
    cache_ok = True

    def process_bind_param(
        self, value: date | datetime | str | None, dialect: Any
    ) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            plaintext = value.date().isoformat()
        elif isinstance(value, date):
            plaintext = value.isoformat()
        elif isinstance(value, str):
            plaintext = date.fromisoformat(value).isoformat()
        else:
            raise TypeError(
                "EncryptedDate only accepts date, datetime, string, or None"
            )
        return DataProtectionCipher().encrypt(plaintext)

    def process_result_value(
        self, value: str | date | None, dialect: Any
    ) -> date | None:
        if value is None:
            return None
        if isinstance(value, date):
            # Compatibility for a connection reading rows before the Date-Text migration
            return value
        plaintext = DataProtectionCipher().decrypt(value)
        return date.fromisoformat(plaintext)


class EncryptedJSON(TypeDecorator[Any]):
    """Transparent encryption for structured JSON audit values."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        import json

        return DataProtectionCipher().encrypt(
            json.dumps(value, separators=(",", ":"), default=str)
        )

    def process_result_value(
        self, value: str | dict[str, Any] | list[Any] | None, dialect: Any
    ) -> Any:
        if value is None:
            return None
        import json

        if isinstance(value, (dict, list)):
            # Compatibility while reading pre-migration JSON from a test database.
            return value
        plaintext = DataProtectionCipher().decrypt(value)
        try:
            return json.loads(plaintext)
        except json.JSONDecodeError as exc:
            raise DataProtectionError("Encrypted JSON contains invalid JSON") from exc
