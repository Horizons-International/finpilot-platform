from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.repositories.base_repository import BaseRepository


class CustomerRiskProfileRepository(BaseRepository[CustomerRiskProfile]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> None:
        super().__init__(
            db,
            CustomerRiskProfile,
        )
        self.tenant_id = tenant_id

    def get_by_id(
        self,
        profile_id: UUID,
    ) -> CustomerRiskProfile | None:
        return (
            self.db.query(CustomerRiskProfile)
            .join(
                Customer,
                Customer.id == CustomerRiskProfile.customer_id,
            )
            .filter(
                CustomerRiskProfile.id == profile_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )

    def get_by_customer_id(
        self,
        customer_id: UUID,
    ) -> CustomerRiskProfile | None:
        return (
            self.db.query(CustomerRiskProfile)
            .join(
                Customer,
                Customer.id == CustomerRiskProfile.customer_id,
            )
            .filter(
                CustomerRiskProfile.customer_id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )

    def get_all(self) -> list[CustomerRiskProfile]:
        return (
            self.db.query(CustomerRiskProfile)
            .join(
                Customer,
                Customer.id == CustomerRiskProfile.customer_id,
            )
            .filter(
                Customer.tenant_id == self.tenant_id,
            )
            .order_by(
                CustomerRiskProfile.assessed_at.desc(),
            )
            .all()
        )
