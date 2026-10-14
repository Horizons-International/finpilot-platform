from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.services.security_event_service import record_security_event
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

        security_event_type = {
            "LOGIN_SUCCESS": "LOGIN_SUCCESS",
            "LOGIN_FAILURE": "LOGIN_FAILURE",
            "PASSWORD_CHANGE": "PASSWORD_CHANGED",
            "USER_ROLE_CHANGED": "PERMISSION_CHANGED",
            "USER_STATUS_CHANGED": "USER_STATUS_CHANGED",
            "USER_DELETED": "USER_DELETED",
            "API_KEY_CREATED": "API_KEY_CREATED",
            "API_KEY_REVOKED": "API_KEY_REVOKED",
            "ACCESS_DENIED": "ACCESS_DENIED",
        }.get(event_type.value)
        if security_event_type is not None:
            record_security_event(
                self.db,
                event_type=security_event_type,
                user_id=user_id,
                tenant_id=self.db.info.get("tenant_id"),
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                details={
                    "resource_type": resource_type,
                    "resource_id": (
                        str(resource_id) if resource_id is not None else None
                    ),
                },
            )

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
