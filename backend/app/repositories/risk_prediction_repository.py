from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.risk_prediction import RiskPrediction


class RiskPredictionRepository:
    def __init__(
        self,
        db: Session,
    ) -> None:
        self.db = db

    def create(
        self,
        prediction: RiskPrediction,
    ) -> RiskPrediction:
        self.db.add(prediction)
        self.db.flush()
        self.db.refresh(prediction)

        return prediction

    def get_by_id(
        self,
        prediction_id: UUID,
    ) -> RiskPrediction | None:
        return self.db.scalar(
            select(RiskPrediction).where(
                RiskPrediction.id == prediction_id,
            )
        )

    def get_latest_for_customer(
        self,
        customer_id: UUID,
    ) -> RiskPrediction | None:
        statement = (
            select(RiskPrediction)
            .where(
                RiskPrediction.customer_id == customer_id,
            )
            .order_by(
                RiskPrediction.created_at.desc(),
            )
            .limit(1)
        )

        return self.db.scalars(statement).first()

    def get_all_for_customer(
        self,
        customer_id: UUID,
    ) -> list[RiskPrediction]:
        statement = (
            select(RiskPrediction)
            .where(
                RiskPrediction.customer_id == customer_id,
            )
            .order_by(
                RiskPrediction.created_at.desc(),
            )
        )

        return list(
            self.db.scalars(statement).all(),
        )
