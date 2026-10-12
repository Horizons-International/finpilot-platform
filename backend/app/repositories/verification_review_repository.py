from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.verification_case import IdentityVerificationCase
from app.models.verification_review import VerificationReview
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class VerificationReviewRepository(TenantScopedRepository[VerificationReview]):
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        # Explicit tenant_id is normally provided by VerificationReviewService;
        # db.info covers authenticated paths that construct the repository later.
        from app.repositories.tenant_scoped_repository import resolve_tenant_id

        resolved = resolve_tenant_id(db, tenant_id)
        assert resolved is not None
        super().__init__(db, VerificationReview, resolved)

    def create(self, review: VerificationReview) -> VerificationReview:
        if review.tenant_id is not None and review.tenant_id != self.tenant_id:
            raise ValueError("Cannot create a review for another tenant.")

        case_exists = self.db.scalar(
            select(IdentityVerificationCase.id).where(
                IdentityVerificationCase.id == review.verification_case_id,
                IdentityVerificationCase.tenant_id == self.tenant_id,
            )
        )
        if case_exists is None:
            raise ValueError("Verification review case is outside this tenant.")

        reviewer_exists = self.db.scalar(
            select(User.id).where(
                User.id == review.reviewer_id,
                User.tenant_id == self.tenant_id,
                User.is_deleted.is_(False),
            )
        )
        if reviewer_exists is None:
            raise ValueError("Verification review reviewer is outside this tenant.")

        return super().create(review)

    def update(self, review: VerificationReview) -> VerificationReview:
        if review.tenant_id != self.tenant_id:
            raise ValueError("Cannot update a review owned by another tenant.")
        case_exists = self.db.scalar(
            select(IdentityVerificationCase.id).where(
                IdentityVerificationCase.id == review.verification_case_id,
                IdentityVerificationCase.tenant_id == self.tenant_id,
            )
        )
        if case_exists is None:
            raise ValueError("Verification review case is outside this tenant.")
        reviewer_exists = self.db.scalar(
            select(User.id).where(
                User.id == review.reviewer_id,
                User.tenant_id == self.tenant_id,
                User.is_deleted.is_(False),
            )
        )
        if reviewer_exists is None:
            raise ValueError("Verification review reviewer is outside this tenant.")
        return super().update(review)

    def get_by_id(self, review_id: UUID) -> VerificationReview | None:
        return self.query().filter(VerificationReview.id == review_id).first()

    def get_by_verification_case_id(
        self,
        verification_case_id: UUID,
    ) -> list[VerificationReview]:
        return (
            self.query()
            .filter(VerificationReview.verification_case_id == verification_case_id)
            .order_by(VerificationReview.created_at.desc())
            .all()
        )

    def get_by_reviewer_id(self, reviewer_id: UUID) -> list[VerificationReview]:
        return (
            self.query()
            .filter(VerificationReview.reviewer_id == reviewer_id)
            .order_by(VerificationReview.created_at.desc())
            .all()
        )
