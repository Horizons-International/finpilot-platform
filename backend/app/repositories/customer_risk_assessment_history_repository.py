from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_risk_assessment_history import (
    CustomerRiskAssessmentHistory,
)


class CustomerRiskAssessmentHistoryRepository:
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id

    def create(
        self,
        history: CustomerRiskAssessmentHistory,
    ) -> CustomerRiskAssessmentHistory:
        self.db.add(history)
        self.db.flush()
        self.db.refresh(history)

        return history

    def get_by_customer(
        self,
        customer_id: UUID,
    ) -> list[CustomerRiskAssessmentHistory]:
        statement = (
            select(CustomerRiskAssessmentHistory)
            .join(
                Customer,
                Customer.id == CustomerRiskAssessmentHistory.customer_id,
            )
            .where(
                CustomerRiskAssessmentHistory.customer_id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .order_by(
                CustomerRiskAssessmentHistory.assessed_at.asc(),
            )
        )

        return list(self.db.scalars(statement).all())
