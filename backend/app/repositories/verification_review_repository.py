from uuid import UUID

from sqlalchemy.orm import Session

from app.models.verification_review import VerificationReview
from app.repositories.base_repository import BaseRepository


class VerificationReviewRepository(BaseRepository[VerificationReview]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, VerificationReview)

    def get_by_id(
        self,
        review_id: UUID,
    ) -> VerificationReview | None:
        return (
            self.db.query(VerificationReview)
            .filter(VerificationReview.id == review_id)
            .first()
        )

    def get_by_verification_case_id(
        self,
        verification_case_id: UUID,
    ) -> list[VerificationReview]:
        return (
            self.db.query(VerificationReview)
            .filter(VerificationReview.verification_case_id == verification_case_id)
            .order_by(VerificationReview.created_at.desc())
            .all()
        )

    def get_by_reviewer_id(
        self,
        reviewer_id: UUID,
    ) -> list[VerificationReview]:
        return (
            self.db.query(VerificationReview)
            .filter(
                VerificationReview.reviewer_id == reviewer_id,
            )
            .order_by(VerificationReview.created_at.desc())
            .all()
        )
