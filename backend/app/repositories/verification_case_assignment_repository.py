from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.verification_case import IdentityVerificationCase
from app.models.verification_case_assignment_history import (
    VerificationCaseAssignmentHistory,
)


class VerificationCaseAssignmentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_case_for_update(
        self,
        *,
        customer_id: UUID,
        verification_case_id: UUID,
    ) -> IdentityVerificationCase | None:
        statement = (
            select(IdentityVerificationCase)
            .where(
                IdentityVerificationCase.id == verification_case_id,
                IdentityVerificationCase.customer_id == customer_id,
            )
            .with_for_update()
        )

        return self.db.scalar(statement)

    def get_reviewer(
        self,
        reviewer_id: UUID,
    ) -> User | None:
        return self.db.scalar(
            select(User).where(
                User.id == reviewer_id,
            )
        )

    def assign_case(
        self,
        case: IdentityVerificationCase,
    ) -> IdentityVerificationCase:
        self.db.flush()
        self.db.refresh(case)

        return case

    def create_history(
        self,
        history: VerificationCaseAssignmentHistory,
    ) -> VerificationCaseAssignmentHistory:
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
                VerificationCaseAssignmentHistory.verification_case_id
                == verification_case_id,
            )
            .order_by(VerificationCaseAssignmentHistory.assigned_at.desc())
        )

        return list(self.db.scalars(statement).all())

    def get_assigned_cases(
        self,
        reviewer_id: UUID,
    ) -> list[IdentityVerificationCase]:
        statement = (
            select(IdentityVerificationCase)
            .where(
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
        )

        return self.db.scalar(statement)

    def get_all_assigned_cases(
        self,
    ) -> list[IdentityVerificationCase]:
        statement = (
            select(IdentityVerificationCase)
            .where(
                IdentityVerificationCase.assigned_to.is_not(None),
            )
            .order_by(
                IdentityVerificationCase.assigned_at.desc().nullslast(),
                IdentityVerificationCase.created_at.desc(),
            )
        )

        return list(self.db.scalars(statement).all())
