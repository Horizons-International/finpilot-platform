"""Encrypted, path-confined local storage compatible with FinPilot's BaseStorage API."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.core.data_protection import DataProtectionError
from app.storages.base_storage import BaseStorage


class LocalStorage(BaseStorage):
    """Encrypts newly written files with AES-256-GCM and reads legacy plaintext files.

    Legacy files can be migrated using ``app.maintenance.encrypt_existing_data``.
    The file path (relative to the configured root) is authenticated as AAD to
    prevent a valid encrypted file being swapped into another path unnoticed.
    """

    MAGIC = b"FPENC1"
    NONCE_SIZE = 12

    def __init__(self, base_path: str):
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._aes = AESGCM(self._key_material())

    @staticmethod
    def _key_material() -> bytes:
        configured = getattr(settings, "DATA_PROTECTION_KEY", "")
        if configured:
            try:
                key = base64.urlsafe_b64decode(configured.encode("ascii"))
            except Exception as exc:
                raise DataProtectionError("DATA_PROTECTION_KEY is invalid") from exc
            if len(key) != 32:
                raise DataProtectionError("DATA_PROTECTION_KEY must encode 32 bytes")
            return key
        if getattr(settings, "ENVIRONMENT", "development") == "production":
            raise DataProtectionError(
                "DATA_PROTECTION_KEY must be configured in production"
            )
        secret = getattr(settings, "SECRET_KEY", "")
        if not secret:
            raise DataProtectionError(
                "SECRET_KEY is required for encrypted local storage"
            )
        return hashlib.sha256(
            (secret + ":finpilot-file-encryption-v1").encode()
        ).digest()

    def _safe_path(self, supplied_path: str | Path) -> Path:
        path = Path(supplied_path)
        if not path.is_absolute():
            path = self.base_path / path
        resolved = path.resolve()
        if resolved != self.base_path and self.base_path not in resolved.parents:
            raise DataProtectionError("Storage path escapes configured storage root")
        return resolved

    def _aad(self, path: Path) -> bytes:
        return path.relative_to(self.base_path).as_posix().encode("utf-8")

    def save(self, file_content: bytes, filename: str, folder: str) -> str:
        # Do not place the original (possibly sensitive) filename in the path.
        raw_name = Path(filename).name
        suffix = Path(raw_name).suffix.lower()
        if len(suffix) > 12 or not suffix.replace(".", "").isalnum():
            suffix = ""
        relative_folder = Path(folder)
        if relative_folder.is_absolute() or ".." in relative_folder.parts:
            raise DataProtectionError("Invalid storage folder")
        folder_path = self._safe_path(relative_folder)
        folder_path.mkdir(parents=True, exist_ok=True)
        path = self._safe_path(folder_path / f"{uuid4().hex}{suffix}")
        nonce = os.urandom(self.NONCE_SIZE)
        ciphertext = self._aes.encrypt(nonce, file_content, self._aad(path))
        path.write_bytes(self.MAGIC + nonce + ciphertext)
        return str(path)

    def read(self, storage_path: str) -> bytes:
        path = self._safe_path(storage_path)
        raw = path.read_bytes()
        if not raw.startswith(self.MAGIC):
            # Rolling deployment compatibility for pre-existing unencrypted files.
            return raw
        minimum = len(self.MAGIC) + self.NONCE_SIZE + 16
        if len(raw) < minimum:
            raise DataProtectionError("Encrypted file is truncated")
        offset = len(self.MAGIC)
        nonce = raw[offset : offset + self.NONCE_SIZE]
        ciphertext = raw[offset + self.NONCE_SIZE :]
        try:
            return self._aes.decrypt(nonce, ciphertext, self._aad(path))
        except Exception as exc:
            raise DataProtectionError("File authentication/decryption failed") from exc

    def delete(self, storage_path: str) -> None:
        path = self._safe_path(storage_path)
        if path.exists():
            path.unlink()

    def exists(self, storage_path: str) -> bool:
        return self._safe_path(storage_path).exists()

    def encrypt_legacy_file(self, path: Path) -> bool:
        """Encrypt a plaintext file in-place; return whether it changed."""
        resolved = self._safe_path(path)
        raw = resolved.read_bytes()
        if raw.startswith(self.MAGIC):
            return False
        nonce = os.urandom(self.NONCE_SIZE)
        encrypted = (
            self.MAGIC + nonce + self._aes.encrypt(nonce, raw, self._aad(resolved))
        )
        temp = resolved.with_name(f".{resolved.name}.{uuid4().hex}.tmp")
        try:
            temp.write_bytes(encrypted)
            os.replace(temp, resolved)
        finally:
            if temp.exists():
                temp.unlink()
        return True
