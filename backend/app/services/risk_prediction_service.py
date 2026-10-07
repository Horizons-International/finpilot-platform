from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.risk_prediction import RiskPrediction
from app.repositories.risk_prediction_feature_repository import (
    RiskPredictionFeatureRepository,
)
from app.repositories.risk_prediction_repository import (
    RiskPredictionRepository,
)
from app.risk_prediction.rule_based import (
    RuleBasedRiskPredictionModel,
)
from app.services.audit_service import AuditService
from app.services.risk_prediction_feature_service import (
    RiskPredictionFeatureService,
)
from app.utils.enums import AuditEventType
from app.utils.errors import not_found


class RiskPredictionService:
    def __init__(
        self,
        db: Session,
    ) -> None:
        self.db = db

        self.repository = RiskPredictionRepository(
            db,
        )

        self.model = RuleBasedRiskPredictionModel()

        self.feature_service = RiskPredictionFeatureService(
            RiskPredictionFeatureRepository(db),
        )

        self.audit_service = AuditService(db)

    def predict_and_store(
        self,
        *,
        customer_id: UUID,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RiskPrediction:
        features = self.feature_service.build_features(
            customer_id,
        )

        prediction = self.model.predict(
            features,
        )

        record = RiskPrediction(
            customer_id=customer_id,
            model_version=self.model.version,
            risk_probability=Decimal(
                str(prediction.risk_probability),
            ),
            features=features.to_dict(),
        )

        self.repository.create(
            record,
        )

        self.audit_service.log_event(
            event_type=AuditEventType.RISK_PREDICTION_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="risk_prediction",
            resource_id=record.id,
        )

        self.db.commit()
        self.db.refresh(record)

        return record

    def get_latest(
        self,
        *,
        customer_id: UUID,
    ) -> RiskPrediction:
        prediction = self.repository.get_latest_for_customer(
            customer_id,
        )

        if prediction is None:
            raise not_found("Risk prediction")

        return prediction

    def get_history(
        self,
        *,
        customer_id: UUID,
    ) -> list[RiskPrediction]:
        return self.repository.get_all_for_customer(
            customer_id,
        )
