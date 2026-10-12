from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_risk_assessment_history import CustomerRiskAssessmentHistory
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class CustomerRiskAssessmentHistoryRepository(
    TenantScopedRepository[CustomerRiskAssessmentHistory]
):
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(db, CustomerRiskAssessmentHistory, tenant_id)

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

    def create(
        self,
        history: CustomerRiskAssessmentHistory,
    ) -> CustomerRiskAssessmentHistory:
        self._ensure_customer_belongs_to_tenant(history.customer_id)
        return super().create(history)

    def update(
        self,
        history: CustomerRiskAssessmentHistory,
    ) -> CustomerRiskAssessmentHistory:
        self._ensure_customer_belongs_to_tenant(history.customer_id)
        return super().update(history)

    def get_by_customer(self, customer_id: UUID) -> list[CustomerRiskAssessmentHistory]:
        return (
            self.query()
            .filter(CustomerRiskAssessmentHistory.customer_id == customer_id)
            .order_by(CustomerRiskAssessmentHistory.assessed_at.asc())
            .all()
        )
