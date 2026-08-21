from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditEventType, AuditLog
from app.repositories.base_repository import BaseRepository


class AuditRepository(BaseRepository[AuditLog]):
    def __init__(self, db: Session):
        super().__init__(db, AuditLog)

    def get_by_user(
        self,
        user_id: UUID,
    ) -> list[AuditLog]:
        return (
            self.db.query(AuditLog)
            .filter(AuditLog.user_id == user_id)
            .order_by(AuditLog.timestamp.desc())
            .all()
        )

    def get_by_event_type(
        self,
        event_type: AuditEventType,
    ) -> list[AuditLog]:
        return (
            self.db.query(AuditLog)
            .filter(AuditLog.event_type == event_type)
            .order_by(AuditLog.timestamp.desc())
            .all()
        )
