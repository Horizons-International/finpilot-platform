from uuid import UUID

from sqlalchemy.orm import Session

from app.models.verification_case import IdentityVerificationCase
from app.repositories.base_repository import BaseRepository


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
