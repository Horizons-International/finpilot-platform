from typing import NoReturn
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.audit_service import AuditService
from app.utils.enums import AuditEventType
from app.utils.errors import not_found


def deny_tenant_access(
    db: Session,
    *,
    user_id: UUID | None,
    email: str | None,
    ip_address: str | None,
    user_agent: str | None,
    resource_type: str,
    resource_id: UUID,
    resource_name: str,
) -> NoReturn:
    """Audit an inaccessible resource, then return a generic not-found error."""

    # Clear any read transaction before persisting the security event.
    db.rollback()

    AuditService(db).log_event(
        event_type=AuditEventType.ACCESS_DENIED,
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        resource_type=resource_type,
        resource_id=resource_id,
    )

    # AuditService.log_event() flushes but does not commit.
    db.commit()

    raise not_found(resource_name)
