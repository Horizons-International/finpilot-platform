"""Helpers for writing tenant-aware security events."""

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.security_event import SecurityEvent
from app.repositories.security_repository import SecurityRepository


def record_security_event(
    db: Session,
    *,
    event_type: str,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    email: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_path: str | None = None,
    details: dict[str, Any] | None = None,
    commit: bool = False,
) -> SecurityEvent:
    resolved_tenant_id = (
        tenant_id if tenant_id is not None else db.info.get("tenant_id")
    )
    event = SecurityEvent(
        tenant_id=resolved_tenant_id,
        user_id=user_id,
        email=email[:255] if email else None,
        event_type=event_type[:64],
        ip_address=ip_address[:45] if ip_address else None,
        user_agent=user_agent[:500] if user_agent else None,
        request_path=request_path[:500] if request_path else None,
        details=details or {},
    )
    SecurityRepository(db, tenant_id=resolved_tenant_id).create_event(event)
    if commit:
        db.commit()
    return event
