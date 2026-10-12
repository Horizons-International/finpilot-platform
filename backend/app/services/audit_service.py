from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.utils.enums import AuditEventType


class AuditService:
    """Create audit entries with tenant ownership inherited from trusted context.

    Global/platform operations may not have tenant context; for those, the model
    must allow a nullable tenant_id and platform audit access must be separately
    authorized.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def log_event(
        self,
        *,
        event_type: AuditEventType,
        user_id: UUID | None = None,
        email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
    ) -> AuditLog:
        audit_log = AuditLog(
            tenant_id=self.db.info.get("tenant_id"),
            event_type=event_type,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        self.db.add(audit_log)
        self.db.flush()
        return audit_log

    def log_access_denied(
        self,
        *,
        resource_type: str,
        resource_id: UUID | None,
        user_id: UUID | None = None,
        email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.log_event(
            event_type=AuditEventType.ACCESS_DENIED,
            user_id=user_id,
            email=email,
            user_agent=user_agent,
            ip_address=ip_address,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        # Persist the security event before the request raises 404/403.
        self.db.commit()
