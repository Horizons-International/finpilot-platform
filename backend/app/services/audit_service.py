"""Existing FinPilot audit service with additive `audit_events` mirroring.

This replacement preserves the current `audit_logs` and security-event behavior;
all existing callers automatically create a normalized immutable audit event.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.repositories.audit_repository import AuditRepository
from app.services.audit_event_service import record_audit_event
from app.services.security_event_service import record_security_event
from app.utils.enums import AuditEventType


class AuditService:
    """Create legacy and append-only audit entries in the current transaction."""

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
        tenant_id = self.db.info.get("tenant_id")
        audit_log = AuditLog(
            tenant_id=tenant_id,
            event_type=event_type,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        AuditRepository.create_event(self.db, audit_log)

        # This metadata intentionally excludes request/response bodies and field
        # values. The sanitizer redacts credential/document-value keys if callers
        # add them later.
        record_audit_event(
            self.db,
            action=event_type.value,
            user_id=user_id,
            entity_type=resource_type,
            entity_id=resource_id,
            metadata={
                "legacy_event_type": event_type.value,
                "email": email,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "request_id": self.db.info.get("request_id"),
            },
        )

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
                tenant_id=tenant_id,
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
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        # Persist the security event before the request raises 404/403.
        self.db.commit()
