from uuid import UUID

from sqlalchemy.orm import Session

from app.models.verification_case import IdentityVerificationCase
from app.repositories.tenant_scoped_repository import (
    TenantScopedRepository,
)
from app.utils.enums import VerificationStatus, VerificationType


class VerificationCaseRepository(TenantScopedRepository[IdentityVerificationCase]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> None:
        super().__init__(
            db=db,
            model=IdentityVerificationCase,
            tenant_id=tenant_id,
        )

    def get_by_customer_id(
        self,
        customer_id: UUID,
    ) -> list[IdentityVerificationCase]:
        return (
            self.query()
            .filter(IdentityVerificationCase.customer_id == customer_id)
            .order_by(IdentityVerificationCase.created_at.desc())
            .all()
        )

    def get_active_by_customer_and_type(
        self,
        customer_id: UUID,
        verification_type: VerificationType,
    ) -> IdentityVerificationCase | None:
        return (
            self.query()
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
            self.query()
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
            self.query()
            .filter(
                IdentityVerificationCase.id == verification_case_id,
                IdentityVerificationCase.customer_id == customer_id,
                IdentityVerificationCase.assigned_to == reviewer_id,
            )
            .first()
        )
