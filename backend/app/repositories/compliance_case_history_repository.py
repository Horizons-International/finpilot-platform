from uuid import UUID

from sqlalchemy.orm import Session

from app.models.compliance_case_history import ComplianceCaseHistory
from app.repositories.base_repository import BaseRepository


class ComplianceCaseHistoryRepository(BaseRepository[ComplianceCaseHistory]):
    def __init__(self, db: Session) -> None:
        super().__init__(
            db,
            ComplianceCaseHistory,
        )

    def get_by_case_id(
        self,
        compliance_case_id: UUID,
    ) -> list[ComplianceCaseHistory]:
        return (
            self.db.query(ComplianceCaseHistory)
            .filter(ComplianceCaseHistory.compliance_case_id == compliance_case_id)
            .order_by(
                ComplianceCaseHistory.created_at.asc(),
            )
            .all()
        )
