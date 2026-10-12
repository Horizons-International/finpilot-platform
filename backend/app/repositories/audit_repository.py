from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import AuditEventType


class AuditRepository(TenantScopedRepository[AuditLog]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved_tenant_id = tenant_id or db.info.get("tenant_id")
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for audit log queries.")

        super().__init__(db, AuditLog, resolved_tenant_id)

    def get_by_user(self, user_id: UUID) -> list[AuditLog]:
        return (
            self.query()
            .filter(AuditLog.user_id == user_id)
            .order_by(AuditLog.timestamp.desc())
            .all()
        )

    def get_by_event_type(self, event_type: AuditEventType) -> list[AuditLog]:
        return (
            self.query()
            .filter(AuditLog.event_type == event_type)
            .order_by(AuditLog.timestamp.desc())
            .all()
        )
