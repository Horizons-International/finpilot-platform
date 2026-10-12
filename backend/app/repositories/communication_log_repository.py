from uuid import UUID

from sqlalchemy.orm import Session

from app.models.communication_log import CommunicationLog
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import CommunicationChannel, CommunicationStatus


class CommunicationLogRepository(TenantScopedRepository[CommunicationLog]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved_tenant_id = tenant_id or db.info.get("tenant_id")
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for communication logs.")

        super().__init__(db, CommunicationLog, resolved_tenant_id)

    def list_logs(
        self,
        *,
        channel: CommunicationChannel | None = None,
        status: CommunicationStatus | None = None,
    ) -> list[CommunicationLog]:
        query = self.query()
        if channel is not None:
            query = query.filter(CommunicationLog.channel == channel)
        if status is not None:
            query = query.filter(CommunicationLog.status == status)
        return query.order_by(
            CommunicationLog.sent_at.desc().nullslast(),
        ).all()

    def get_by_id(self, communication_id: UUID) -> CommunicationLog | None:
        return self.query().filter(CommunicationLog.id == communication_id).first()
