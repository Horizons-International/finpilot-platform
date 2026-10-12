from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.risk_prediction import RiskPrediction


class RiskPredictionRepository:
    """Tenant-scoped access to risk predictions."""

    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved_tenant_id = tenant_id or db.info.get("tenant_id")
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for risk predictions.")
        session_tenant_id = db.info.get("tenant_id")
        if session_tenant_id is not None and session_tenant_id != resolved_tenant_id:
            raise ValueError(
                "The SQLAlchemy session is already bound to another tenant."
            )
        # Also scope relationship/lazy loads covered by tenant_filter.py.
        db.info["tenant_id"] = resolved_tenant_id
        self.db = db
        self.tenant_id = resolved_tenant_id

    def create(self, prediction: RiskPrediction) -> RiskPrediction:
        if prediction.tenant_id is not None and prediction.tenant_id != self.tenant_id:
            raise ValueError("Cannot create a risk prediction for another tenant.")

        customer_exists = self.db.scalar(
            select(Customer.id).where(
                Customer.id == prediction.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer_exists is None:
            raise ValueError(
                "Prediction customer does not belong to the current tenant."
            )

        prediction.tenant_id = self.tenant_id
        self.db.add(prediction)
        self.db.flush()
        self.db.refresh(prediction)
        return prediction

    def get_by_id(self, prediction_id: UUID) -> RiskPrediction | None:
        return self.db.scalar(
            select(RiskPrediction).where(
                RiskPrediction.id == prediction_id,
                RiskPrediction.tenant_id == self.tenant_id,
            )
        )

    def get_latest_for_customer(self, customer_id: UUID) -> RiskPrediction | None:
        statement = (
            select(RiskPrediction)
            .where(
                RiskPrediction.customer_id == customer_id,
                RiskPrediction.tenant_id == self.tenant_id,
            )
            .order_by(RiskPrediction.created_at.desc())
            .limit(1)
        )
        return self.db.scalars(statement).first()

    def get_all_for_customer(self, customer_id: UUID) -> list[RiskPrediction]:
        statement = (
            select(RiskPrediction)
            .where(
                RiskPrediction.customer_id == customer_id,
                RiskPrediction.tenant_id == self.tenant_id,
            )
            .order_by(RiskPrediction.created_at.desc())
        )
        return list(self.db.scalars(statement).all())
