from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer_audit_log import CustomerAuditLog
from app.repositories.customer_audit_log_repository import CustomerAuditLogRepository
from app.services.tenant_context import resolve_tenant_context
from app.utils.audit import serialize_audit_value


class CustomerAuditLogService:
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        self.db = db
        self.tenant_id = resolve_tenant_context(
            db, tenant_id, resource_name="customer audit logs"
        )
        self.repository = CustomerAuditLogRepository(db, tenant_id=self.tenant_id)

    def create_audit_log(
        self,
        *,
        customer_id: UUID,
        user_id: UUID,
        resource_type: str,
        resource_id: UUID,
        action: str,
        old_value: object | None,
        new_value: object | None,
    ) -> CustomerAuditLog:
        audit_log = CustomerAuditLog(
            tenant_id=self.tenant_id,
            customer_id=customer_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            old_value=serialize_audit_value(old_value),
            new_value=serialize_audit_value(new_value),
        )
        return self.repository.create(audit_log)

    def get_customer_history(self, customer_id: UUID) -> list[CustomerAuditLog]:
        return self.repository.get_by_customer_id(customer_id)
