"""Small RFC 6238 TOTP implementation with encrypted at-rest seed storage."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def encrypt_totp_secret(secret: str) -> str:
    secret_key = settings.SECRET_KEY.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key).digest())
    return Fernet(key).encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_totp_secret(encrypted_secret: str) -> str:
    secret_key = settings.SECRET_KEY.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key).digest())
    try:
        return Fernet(key).decrypt(encrypted_secret.encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise ValueError("The stored MFA secret could not be decrypted.") from exc


def _totp_at(secret: str, timestamp: int, *, step: int = 30, digits: int = 6) -> str:
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    counter = int(timestamp // step)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10**digits)).zfill(digits)


def verify_totp(
    secret: str, code: str, *, now: int | None = None, window: int = 1
) -> bool:
    code = code.strip()
    if len(code) != 6 or not code.isdigit():
        return False
    timestamp = int(time.time()) if now is None else int(now)
    return any(
        hmac.compare_digest(_totp_at(secret, timestamp + offset * 30), code)
        for offset in range(-window, window + 1)
    )


def build_otpauth_uri(secret: str, email: str) -> str:
    label = quote(f"FinPilot:{email}", safe=":")
    query = urlencode(
        {
            "secret": secret,
            "issuer": "FinPilot",
            "algorithm": "SHA1",
            "digits": 6,
            "period": 30,
        }
    )
    return f"otpauth://totp/{label}?{query}"
