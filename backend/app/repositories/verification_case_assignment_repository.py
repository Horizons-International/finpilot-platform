from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.user import User
from app.models.verification_case import IdentityVerificationCase
from app.models.verification_case_assignment_history import (
    VerificationCaseAssignmentHistory,
)
from app.repositories.tenant_scoped_repository import resolve_tenant_id


class VerificationCaseAssignmentRepository:
    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved = resolve_tenant_id(db, tenant_id)
        assert resolved is not None
        self.db = db
        self.tenant_id = resolved

    def get_case_for_update(
        self,
        *,
        customer_id: UUID,
        verification_case_id: UUID,
    ) -> IdentityVerificationCase | None:
        statement = (
            select(IdentityVerificationCase)
            .join(Customer, Customer.id == IdentityVerificationCase.customer_id)
            .where(
                IdentityVerificationCase.id == verification_case_id,
                IdentityVerificationCase.customer_id == customer_id,
                IdentityVerificationCase.tenant_id == self.tenant_id,
                Customer.tenant_id == self.tenant_id,
            )
            .with_for_update()
        )
        return self.db.scalar(statement)

    def get_reviewer(self, reviewer_id: UUID) -> User | None:
        return self.db.scalar(
            select(User).where(
                User.id == reviewer_id,
                User.tenant_id == self.tenant_id,
                User.is_platform_admin.is_(False),
                User.is_deleted.is_(False),
            )
        )

    def assign_case(self, case: IdentityVerificationCase) -> IdentityVerificationCase:
        if case.tenant_id != self.tenant_id:
            raise ValueError("Cannot assign a verification case from another tenant.")

        customer_exists = self.db.scalar(
            select(Customer.id).where(
                Customer.id == case.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer_exists is None:
            raise ValueError("Verification case customer is outside this tenant.")

        for user_id, label in (
            (case.assigned_to, "reviewer"),
            (case.assigned_by, "assigning user"),
        ):
            if user_id is not None:
                exists = self.db.scalar(
                    select(User.id).where(
                        User.id == user_id,
                        User.tenant_id == self.tenant_id,
                    )
                )
                if exists is None:
                    raise ValueError(
                        f"Verification case {label} is outside this tenant."
                    )

        self.db.flush()
        self.db.refresh(case)
        return case

    def create_history(
        self,
        history: VerificationCaseAssignmentHistory,
    ) -> VerificationCaseAssignmentHistory:
        if history.tenant_id is not None and history.tenant_id != self.tenant_id:
            raise ValueError("Cannot create assignment history for another tenant.")

        case_exists = self.db.scalar(
            select(IdentityVerificationCase.id).where(
                IdentityVerificationCase.id == history.verification_case_id,
                IdentityVerificationCase.tenant_id == self.tenant_id,
            )
        )
        if case_exists is None:
            raise ValueError("Assignment history case is outside this tenant.")

        for user_id, label in (
            (history.assigned_to, "assigned reviewer"),
            (history.assigned_by, "assigning user"),
            (history.previous_reviewer, "previous reviewer"),
        ):
            if user_id is not None:
                exists = self.db.scalar(
                    select(User.id).where(
                        User.id == user_id,
                        User.tenant_id == self.tenant_id,
                    )
                )
                if exists is None:
                    raise ValueError(
                        f"Assignment history {label} is outside this tenant."
                    )

        history.tenant_id = self.tenant_id
        self.db.add(history)
        self.db.flush()
        self.db.refresh(history)
        return history

    def get_history(
        self,
        verification_case_id: UUID,
    ) -> list[VerificationCaseAssignmentHistory]:
        statement = (
            select(VerificationCaseAssignmentHistory)
            .where(
                VerificationCaseAssignmentHistory.tenant_id == self.tenant_id,
                VerificationCaseAssignmentHistory.verification_case_id
                == verification_case_id,
            )
            .order_by(VerificationCaseAssignmentHistory.assigned_at.desc())
        )
        return list(self.db.scalars(statement).all())

    def get_assigned_cases(self, reviewer_id: UUID) -> list[IdentityVerificationCase]:
        statement = (
            select(IdentityVerificationCase)
            .where(
                IdentityVerificationCase.tenant_id == self.tenant_id,
                IdentityVerificationCase.assigned_to == reviewer_id,
            )
            .order_by(
                IdentityVerificationCase.assigned_at.desc().nullslast(),
                IdentityVerificationCase.created_at.desc(),
            )
        )
        return list(self.db.scalars(statement).all())

    def get_case(
        self,
        *,
        customer_id: UUID,
        verification_case_id: UUID,
    ) -> IdentityVerificationCase | None:
        statement = select(IdentityVerificationCase).where(
            IdentityVerificationCase.id == verification_case_id,
            IdentityVerificationCase.customer_id == customer_id,
            IdentityVerificationCase.tenant_id == self.tenant_id,
        )
        return self.db.scalar(statement)

    def get_all_assigned_cases(self) -> list[IdentityVerificationCase]:
        statement = (
            select(IdentityVerificationCase)
            .where(
                IdentityVerificationCase.tenant_id == self.tenant_id,
                IdentityVerificationCase.assigned_to.is_not(None),
            )
            .order_by(
                IdentityVerificationCase.assigned_at.desc().nullslast(),
                IdentityVerificationCase.created_at.desc(),
            )
        )
        return list(self.db.scalars(statement).all())
