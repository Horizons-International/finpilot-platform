"""At-rest encryption and request signing for webhook secrets."""

import base64
import hashlib
import hmac
import json
from typing import Any

from cryptography.fernet import Fernet

from app.core.config import settings


def _fernet() -> Fernet:
    # Derive a stable Fernet key from the configured application secret. A
    # dedicated secret manager/key is recommended for production deployments.
    encryption_secret = settings.WEBHOOK_ENCRYPTION_KEY or settings.SECRET_KEY
    material = ("finpilot-webhook-secret:" + encryption_secret).encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(key)


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_secret(encrypted_secret: str) -> str:
    return _fernet().decrypt(encrypted_secret.encode("ascii")).decode("utf-8")


def canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sign_payload(secret: str, payload: dict[str, Any]) -> str:
    digest = hmac.new(secret.encode("utf-8"), canonical_json(payload), hashlib.sha256)
    return "sha256=" + digest.hexdigest()


def verify_signature(secret: str, payload: dict[str, Any], signature: str) -> bool:
    return hmac.compare_digest(sign_payload(secret, payload), signature)
