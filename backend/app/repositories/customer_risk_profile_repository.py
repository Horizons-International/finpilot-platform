from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class CustomerRiskProfileRepository(TenantScopedRepository[CustomerRiskProfile]):
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(db, CustomerRiskProfile, tenant_id)

    def _ensure_customer_belongs_to_tenant(self, customer_id: UUID) -> None:
        customer_exists = (
            self.db.query(Customer.id)
            .filter(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )
        if customer_exists is None:
            raise ValueError("The customer does not belong to the current tenant.")

    def create(self, profile: CustomerRiskProfile) -> CustomerRiskProfile:
        self._ensure_customer_belongs_to_tenant(profile.customer_id)
        return super().create(profile)

    def update(self, profile: CustomerRiskProfile) -> CustomerRiskProfile:
        self._ensure_customer_belongs_to_tenant(profile.customer_id)
        return super().update(profile)

    def get_by_id(self, profile_id: UUID) -> CustomerRiskProfile | None:
        return (
            self.query()
            .join(Customer, Customer.id == CustomerRiskProfile.customer_id)
            .filter(
                CustomerRiskProfile.id == profile_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )

    def get_by_customer_id(self, customer_id: UUID) -> CustomerRiskProfile | None:
        return (
            self.query()
            .join(Customer, Customer.id == CustomerRiskProfile.customer_id)
            .filter(
                CustomerRiskProfile.customer_id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )

    def get_all(self) -> list[CustomerRiskProfile]:
        return (
            self.query()
            .join(Customer, Customer.id == CustomerRiskProfile.customer_id)
            .filter(Customer.tenant_id == self.tenant_id)
            .order_by(CustomerRiskProfile.assessed_at.desc())
            .all()
        )
