from __future__ import annotations

from uuid import uuid4

from app.services.audit_event_service import sanitize_audit_metadata


def test_metadata_sanitizer_redacts_secrets_and_identity_values() -> None:
    metadata = sanitize_audit_metadata(
        {
            "change": "role updated",
            "password": "p@ssword",
            "document_number": "P1234567",
            "nested": {"access_token": "bearer-secret", "count": 2},
            "entity_id": uuid4(),
        }
    )
    assert metadata["change"] == "role updated"
    assert metadata["password"] == "[REDACTED]"
    assert metadata["document_number"] == "[REDACTED]"
    assert metadata["nested"]["access_token"] == "[REDACTED]"
    assert metadata["nested"]["count"] == 2
    assert isinstance(metadata["entity_id"], str)


def test_metadata_sanitizer_bounds_strings_and_depth() -> None:
    metadata = sanitize_audit_metadata(
        {"note": "x" * 1500, "a": {"b": {"c": {"d": {"e": "deep"}}}}}
    )
    assert len(metadata["note"]) == 1000
    assert metadata["a"]["b"]["c"]["d"]["e"] == "[MAX_DEPTH]"


def test_metadata_sanitizer_accepts_none() -> None:
    assert sanitize_audit_metadata(None) == {}
