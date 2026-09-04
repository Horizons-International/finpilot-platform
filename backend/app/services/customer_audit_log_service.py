from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer_audit_log import CustomerAuditLog
from app.repositories.customer_audit_log_repository import (
    CustomerAuditLogRepository,
)


class CustomerAuditLogService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CustomerAuditLogRepository(db)

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
            customer_id=customer_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            old_value=old_value,
            new_value=new_value,
        )

        return self.repository.create(audit_log)

    def get_customer_history(
        self,
        customer_id: UUID,
    ) -> list[CustomerAuditLog]:
        return self.repository.get_by_customer_id(customer_id)
