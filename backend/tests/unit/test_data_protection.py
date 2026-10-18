from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.data_protection import (
    DataProtectionCipher,
    DataProtectionError,
    EncryptedDate,
    EncryptedJSON,
    EncryptedString,
)
from app.storages.local_storage import LocalStorage


def use_test_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "DATA_PROTECTION_KEY", Fernet.generate_key().decode("ascii")
    )
    monkeypatch.setattr(settings, "ENVIRONMENT", "testing")


def test_encrypted_string_round_trip_and_storage_is_ciphertext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_test_key(monkeypatch)
    field = EncryptedString()
    stored = field.process_bind_param("passport-123", None)
    assert stored is not None and stored.startswith("fpenc:v1:")
    assert "passport-123" not in stored
    assert field.process_result_value(stored, None) == "passport-123"


def test_plaintext_compatibility_for_backfill_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_test_key(monkeypatch)
    assert DataProtectionCipher().decrypt("legacy plaintext") == "legacy plaintext"


def test_tampered_ciphertext_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    use_test_key(monkeypatch)
    cipher = DataProtectionCipher()
    stored = cipher.encrypt("sensitive")
    bad = stored[:-1] + ("A" if stored[-1] != "A" else "B")
    with pytest.raises(DataProtectionError):
        cipher.decrypt(bad)


def test_encrypted_date_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    use_test_key(monkeypatch)
    field = EncryptedDate()
    stored = field.process_bind_param(date(1990, 1, 2), None)
    assert stored and "1990-01-02" not in stored
    assert field.process_result_value(stored, None) == date(1990, 1, 2)


def test_encrypted_json_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    use_test_key(monkeypatch)
    field = EncryptedJSON()
    value = {"date_of_birth": "1990-01-02", "phone_number": "555-0100"}
    stored = field.process_bind_param(value, None)
    assert stored and "555-0100" not in stored
    assert field.process_result_value(stored, None) == value


def test_encrypted_local_storage_round_trip_and_no_filename_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_test_key(monkeypatch)
    storage = LocalStorage(str(tmp_path))
    saved = storage.save(
        b"very sensitive content", "customer-passport-123.pdf", "verification/test"
    )
    assert "customer-passport-123" not in Path(saved).name
    assert Path(saved).read_bytes().startswith(storage.MAGIC)
    assert b"very sensitive content" not in Path(saved).read_bytes()
    assert storage.read(saved) == b"very sensitive content"


def test_encrypted_local_storage_rejects_path_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_test_key(monkeypatch)
    storage = LocalStorage(str(tmp_path / "storage"))
    with pytest.raises(DataProtectionError):
        storage.save(b"secret", "file.txt", "../../outside")


def test_encrypted_local_storage_detects_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_test_key(monkeypatch)
    storage = LocalStorage(str(tmp_path))
    saved = Path(storage.save(b"secret", "test.pdf", "docs"))
    raw = bytearray(saved.read_bytes())
    raw[-1] ^= 0x01
    saved.write_bytes(bytes(raw))
    with pytest.raises(DataProtectionError):
        storage.read(str(saved))
