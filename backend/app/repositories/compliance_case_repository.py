from uuid import UUID

from sqlalchemy.orm import Session

from app.models.compliance_case import ComplianceCase
from app.repositories.base_repository import BaseRepository
from app.utils.enums import (
    ComplianceCaseStatus,
    ComplianceCaseType,
)


class ComplianceCaseRepository(
    BaseRepository[ComplianceCase],
):
    def __init__(self, db: Session) -> None:
        super().__init__(
            db,
            ComplianceCase,
        )

    def get_by_id(
        self,
        case_id: UUID,
    ) -> ComplianceCase | None:
        return (
            self.db.query(ComplianceCase)
            .filter(
                ComplianceCase.id == case_id,
            )
            .first()
        )

    def get_by_customer_id(
        self,
        customer_id: UUID,
    ) -> list[ComplianceCase]:
        return (
            self.db.query(ComplianceCase)
            .filter(
                ComplianceCase.customer_id == customer_id,
            )
            .order_by(
                ComplianceCase.created_at.desc(),
            )
            .all()
        )

    def get_all(
        self,
        *,
        status: ComplianceCaseStatus | None = None,
        case_type: ComplianceCaseType | None = None,
        assigned_to: UUID | None = None,
    ) -> list[ComplianceCase]:
        query = self.db.query(ComplianceCase)

        if status is not None:
            query = query.filter(
                ComplianceCase.status == status,
            )

        if case_type is not None:
            query = query.filter(
                ComplianceCase.case_type == case_type,
            )

        if assigned_to is not None:
            query = query.filter(
                ComplianceCase.assigned_to == assigned_to,
            )

        return query.order_by(
            ComplianceCase.created_at.desc(),
        ).all()

    def get_by_id_and_customer(
        self,
        case_id: UUID,
        customer_id: UUID,
    ) -> ComplianceCase | None:
        return (
            self.db.query(ComplianceCase)
            .filter(
                ComplianceCase.id == case_id,
                ComplianceCase.customer_id == customer_id,
            )
            .first()
        )
