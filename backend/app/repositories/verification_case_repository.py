from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.user import User
from app.models.verification_case import IdentityVerificationCase
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import VerificationStatus, VerificationType


class VerificationCaseRepository(TenantScopedRepository[IdentityVerificationCase]):
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(db=db, model=IdentityVerificationCase, tenant_id=tenant_id)

    def create(self, case: IdentityVerificationCase) -> IdentityVerificationCase:
        customer_exists = self.db.scalar(
            select(Customer.id).where(
                Customer.id == case.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer_exists is None:
            raise ValueError("Verification case customer is outside this tenant.")
        for user_id, label in (
            (case.assigned_to, "assigned reviewer"),
            (case.assigned_by, "assigning user"),
        ):
            if user_id is not None:
                user_exists = self.db.scalar(
                    select(User.id).where(
                        User.id == user_id,
                        User.tenant_id == self.tenant_id,
                    )
                )
                if user_exists is None:
                    raise ValueError(
                        f"Verification case {label} is outside this tenant."
                    )
        return super().create(case)

    def update(self, case: IdentityVerificationCase) -> IdentityVerificationCase:
        if case.tenant_id != self.tenant_id:
            raise ValueError(
                "Cannot update a verification case owned by another tenant."
            )
        customer_exists = self.db.scalar(
            select(Customer.id).where(
                Customer.id == case.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer_exists is None:
            raise ValueError("Verification case customer is outside this tenant.")
        for user_id, label in (
            (case.assigned_to, "assigned reviewer"),
            (case.assigned_by, "assigning user"),
        ):
            if user_id is not None:
                user_exists = self.db.scalar(
                    select(User.id).where(
                        User.id == user_id,
                        User.tenant_id == self.tenant_id,
                    )
                )
                if user_exists is None:
                    raise ValueError(
                        f"Verification case {label} is outside this tenant."
                    )
        return super().update(case)

    def get_by_customer_id(self, customer_id: UUID) -> list[IdentityVerificationCase]:
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
