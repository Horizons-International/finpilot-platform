from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_audit_log import CustomerAuditLog
from app.models.user import User
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class CustomerAuditLogRepository(TenantScopedRepository[CustomerAuditLog]):
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        resolved_tenant_id = (
            tenant_id if tenant_id is not None else db.info.get("tenant_id")
        )
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for customer audit logs.")
        super().__init__(db, CustomerAuditLog, resolved_tenant_id)

    def _ensure_related_records_belong_to_tenant(
        self, audit_log: CustomerAuditLog
    ) -> None:
        customer_exists = (
            self.db.query(Customer.id)
            .filter(
                Customer.id == audit_log.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )
        if customer_exists is None:
            raise ValueError("The customer does not belong to the current tenant.")

        user_exists = (
            self.db.query(User.id)
            .filter(
                User.id == audit_log.user_id,
                User.tenant_id == self.tenant_id,
            )
            .first()
        )
        if user_exists is None:
            raise ValueError("The user does not belong to the current tenant.")

    def create(self, audit_log: CustomerAuditLog) -> CustomerAuditLog:
        self._ensure_related_records_belong_to_tenant(audit_log)
        return super().create(audit_log)

    def update(self, audit_log: CustomerAuditLog) -> CustomerAuditLog:
        self._ensure_related_records_belong_to_tenant(audit_log)
        return super().update(audit_log)

    def get_by_customer_id(self, customer_id: UUID) -> list[CustomerAuditLog]:
        return (
            self.query()
            .filter(CustomerAuditLog.customer_id == customer_id)
            .order_by(CustomerAuditLog.created_at.desc())
            .all()
        )
