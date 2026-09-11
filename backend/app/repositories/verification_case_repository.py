from uuid import UUID

from sqlalchemy.orm import Session

from app.models.verification_case import IdentityVerificationCase
from app.repositories.base_repository import BaseRepository
from app.utils.enums import VerificationStatus


class VerificationCaseRepository(BaseRepository[IdentityVerificationCase]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, IdentityVerificationCase)

    def get_by_customer_id(
        self,
        customer_id: UUID,
    ) -> list[IdentityVerificationCase]:
        return (
            self.db.query(IdentityVerificationCase)
            .filter(
                IdentityVerificationCase.customer_id == customer_id,
            )
            .order_by(IdentityVerificationCase.created_at.desc())
            .all()
        )

    def get_active_by_customer_and_type(
        self,
        customer_id: UUID,
        verification_type: str,
    ) -> IdentityVerificationCase | None:
        return (
            self.db.query(IdentityVerificationCase)
            .filter(
                IdentityVerificationCase.customer_id == customer_id,
                IdentityVerificationCase.verification_type == verification_type,
                IdentityVerificationCase.status.in_(
                    {
                        VerificationStatus.NOT_STARTED,
                        VerificationStatus.PENDING,
                        VerificationStatus.UNDER_REVIEW,
                    }
                ),
            )
            .first()
        )

    def get_by_id_and_customer(
        self,
        verification_case_id: UUID,
        customer_id: UUID,
    ) -> IdentityVerificationCase | None:
        return (
            self.db.query(IdentityVerificationCase)
            .filter(
                IdentityVerificationCase.id == verification_case_id,
                IdentityVerificationCase.customer_id == customer_id,
            )
            .first()
        )

    def get_by_id_and_customer_and_reviewer(
        self,
        verification_case_id: UUID,
        customer_id: UUID,
        reviewer_id: UUID,
    ) -> IdentityVerificationCase | None:
        return (
            self.db.query(IdentityVerificationCase)
            .filter(
                IdentityVerificationCase.id == verification_case_id,
                IdentityVerificationCase.customer_id == customer_id,
                IdentityVerificationCase.assigned_to == reviewer_id,
            )
            .first()
        )
