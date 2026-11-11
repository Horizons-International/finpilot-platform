"""Async audit persistence that keeps audit rows in the caller's transaction."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Table, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent
from app.models.audit_log import AuditLog
from app.models.security_event import SecurityEvent
from app.services.audit_event_service import sanitize_audit_metadata
from app.utils.enums import AuditEventType

_SECURITY_EVENT_TYPES = {
    "LOGIN_SUCCESS": "LOGIN_SUCCESS",
    "LOGIN_FAILURE": "LOGIN_FAILURE",
    "PASSWORD_CHANGE": "PASSWORD_CHANGED",
    "USER_ROLE_CHANGED": "PERMISSION_CHANGED",
    "USER_STATUS_CHANGED": "USER_STATUS_CHANGED",
    "USER_DELETED": "USER_DELETED",
    "API_KEY_CREATED": "API_KEY_CREATED",
    "API_KEY_REVOKED": "API_KEY_REVOKED",
    "ACCESS_DENIED": "ACCESS_DENIED",
}


class AsyncAuditService:
    """Write legacy audit logs, immutable audit events and security events."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log_event(
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
        if tenant_id is not None and not isinstance(tenant_id, UUID):
            raise ValueError("Audit tenant context must be a UUID.")

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
        self.db.add(audit_log)

        metadata: dict[str, Any] = sanitize_audit_metadata(
            {
                "legacy_event_type": event_type.value,
                "email": email,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "request_id": self.db.info.get("request_id"),
            }
        )

        if tenant_id is None:
            # The tenant guard permits global AuditLog/SecurityEvent ORM writes,
            # but global AuditEvent rows must use a reviewed Core insert.
            audit_event_table = cast(Table, AuditEvent.__table__)

            statement = (
                insert(audit_event_table)
                .values(
                    id=uuid4(),
                    tenant_id=None,
                    user_id=user_id,
                    action=event_type.value[:100],
                    entity_type=resource_type,
                    entity_id=resource_id,
                    metadata=metadata,
                )
                .execution_options(
                    skip_tenant_filter=True,
                    tenant_scope_reason=("record global or anonymous audit evidence"),
                )
            )
            await self.db.execute(statement)
        else:
            self.db.add(
                AuditEvent(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action=event_type.value[:100],
                    entity_type=resource_type,
                    entity_id=resource_id,
                    event_metadata=metadata,
                )
            )

        security_event_type = _SECURITY_EVENT_TYPES.get(event_type.value)
        if security_event_type is not None:
            self.db.add(
                SecurityEvent(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    email=email[:255] if email else None,
                    event_type=security_event_type[:64],
                    ip_address=ip_address[:45] if ip_address else None,
                    user_agent=user_agent[:500] if user_agent else None,
                    details={
                        "resource_type": resource_type,
                        "resource_id": (
                            str(resource_id) if resource_id is not None else None
                        ),
                    },
                )
            )

        await self.db.flush()
        return audit_log

    async def log_access_denied(
        self,
        *,
        resource_type: str,
        resource_id: UUID | None,
        user_id: UUID | None = None,
        email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        await self.log_event(
            event_type=AuditEventType.ACCESS_DENIED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        await self.db.commit()
