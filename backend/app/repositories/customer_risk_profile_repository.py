from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer_risk_profile import CustomerRiskProfile
from app.repositories.base_repository import BaseRepository


class CustomerRiskProfileRepository(BaseRepository[CustomerRiskProfile]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, CustomerRiskProfile)

    def get_by_id(
        self,
        profile_id: UUID,
    ) -> CustomerRiskProfile | None:
        return (
            self.db.query(CustomerRiskProfile)
            .filter(CustomerRiskProfile.id == profile_id)
            .first()
        )

    def get_by_customer_id(
        self,
        customer_id: UUID,
    ) -> CustomerRiskProfile | None:
        return (
            self.db.query(CustomerRiskProfile)
            .filter(
                CustomerRiskProfile.customer_id == customer_id,
            )
            .first()
        )

    def get_all(self) -> list[CustomerRiskProfile]:
        return (
            self.db.query(CustomerRiskProfile)
            .order_by(CustomerRiskProfile.assessed_at.desc())
            .all()
        )
