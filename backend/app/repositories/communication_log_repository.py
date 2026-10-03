from uuid import UUID

from sqlalchemy.orm import Session

from app.models.communication_log import CommunicationLog
from app.repositories.base_repository import BaseRepository
from app.utils.enums import CommunicationChannel, CommunicationStatus


class CommunicationLogRepository(BaseRepository[CommunicationLog]):
    def __init__(
        self,
        db: Session,
    ) -> None:
        super().__init__(
            db,
            CommunicationLog,
        )

    def list_logs(
        self,
        *,
        channel: CommunicationChannel | None = None,
        status: CommunicationStatus | None = None,
    ) -> list[CommunicationLog]:
        query = self.db.query(CommunicationLog)

        if channel is not None:
            query = query.filter(
                CommunicationLog.channel == channel,
            )

        if status is not None:
            query = query.filter(
                CommunicationLog.status == status,
            )

        return query.order_by(
            CommunicationLog.sent_at.desc().nullslast(),
        ).all()

    def get_by_id(
        self,
        communication_id: UUID,
    ) -> CommunicationLog | None:
        return (
            self.db.query(CommunicationLog)
            .filter(
                CommunicationLog.id == communication_id,
            )
            .first()
        )
