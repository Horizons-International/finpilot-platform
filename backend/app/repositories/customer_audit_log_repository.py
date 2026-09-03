from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer_audit_log import CustomerAuditLog
from app.repositories.base_repository import BaseRepository


class CustomerAuditLogRepository(BaseRepository[CustomerAuditLog]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, CustomerAuditLog)

    def get_by_customer_id(
        self,
        customer_id: UUID,
    ) -> list[CustomerAuditLog]:
        return (
            self.db.query(CustomerAuditLog)
            .filter(CustomerAuditLog.customer_id == customer_id)
            .order_by(CustomerAuditLog.created_at.desc())
            .all()
        )
