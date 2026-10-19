from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError

from app.models.audit_event import AuditEvent
from app.services.audit_event_service import AuditEventService
from app.utils.enums import UserRole


def test_event_is_written_and_searched_with_tenant_scope(db_session, create_test_user):
    user = create_test_user(
        role=UserRole.ADMINISTRATOR, email="audit-event-create@example.com"
    )
    tenant_id = user.tenant_id
    db_session.info["tenant_id"] = tenant_id
    service = AuditEventService(db_session, tenant_id)
    event = service.record_event(
        action="VERIFICATION_DECISION",
        user_id=user.id,
        entity_type="verification_case",
        entity_id=uuid4(),
        metadata={"decision": "APPROVED", "document_number": "should-be-redacted"},
    )
    db_session.commit()

    assert event.tenant_id == tenant_id
    assert event.event_metadata["decision"] == "APPROVED"
    assert event.event_metadata["document_number"] == "[REDACTED]"
    rows, total = service.search(action="VERIFICATION_DECISION", page=1, page_size=10)
    assert total >= 1
    assert any(row.id == event.id for row in rows)


def test_bulk_update_is_rejected_by_database_trigger(db_session, create_test_user):
    user = create_test_user(
        role=UserRole.ADMINISTRATOR, email="audit-event-immutable@example.com"
    )
    db_session.info["tenant_id"] = user.tenant_id
    service = AuditEventService(db_session, user.tenant_id)
    item = service.record_event(action="AUDIT_IMMUTABILITY_TEST", user_id=user.id)
    db_session.commit()

    with pytest.raises(DBAPIError):
        db_session.execute(
            update(AuditEvent).where(AuditEvent.id == item.id).values(action="TAMPERED")
        )
        db_session.commit()
    db_session.rollback()


def test_api_search_requires_authentication(client):
    response = client.get("/api/v1/audit-events")
    assert response.status_code in {401, 403}
