from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.risk_prediction import RiskPrediction
from app.repositories.risk_prediction_feature_repository import (
    RiskPredictionFeatureRepository,
)
from app.repositories.risk_prediction_repository import RiskPredictionRepository
from app.risk_prediction.rule_based import RuleBasedRiskPredictionModel
from app.services.audit_service import AuditService
from app.services.risk_prediction_feature_service import RiskPredictionFeatureService
from app.services.tenant_context import resolve_tenant_context
from app.utils.enums import AuditEventType
from app.utils.errors import not_found


class RiskPredictionService:
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        self.db = db
        self._requested_tenant_id = tenant_id
        self.tenant_id: UUID | None = tenant_id
        self.repository: RiskPredictionRepository | None = None
        self.feature_service: RiskPredictionFeatureService | None = None
        self.model = RuleBasedRiskPredictionModel()
        self.audit_service = AuditService(db)

    def _bind_tenant(self) -> UUID:
        tenant_id = resolve_tenant_context(
            self.db, self._requested_tenant_id, resource_name="risk predictions"
        )
        self.tenant_id = tenant_id
        if self.repository is None:
            self.repository = RiskPredictionRepository(self.db, tenant_id=tenant_id)
        if self.feature_service is None:
            self.feature_service = RiskPredictionFeatureService(
                RiskPredictionFeatureRepository(self.db, tenant_id=tenant_id)
            )
        return tenant_id

    def predict_and_store(
        self,
        *,
        customer_id: UUID,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RiskPrediction:
        tenant_id = self._bind_tenant()
        assert self.feature_service is not None and self.repository is not None
        features = self.feature_service.build_features(customer_id)
        prediction = self.model.predict(features)
        record = RiskPrediction(
            tenant_id=tenant_id,
            customer_id=customer_id,
            model_version=self.model.version,
            risk_probability=Decimal(str(prediction.risk_probability)),
            features=features.to_dict(),
        )
        record = self.repository.create(record)
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

    def get_latest(self, *, customer_id: UUID) -> RiskPrediction:
        self._bind_tenant()
        assert self.repository is not None
        prediction = self.repository.get_latest_for_customer(customer_id)
        if prediction is None:
            raise not_found("Risk prediction")
        return prediction

    def get_history(self, *, customer_id: UUID) -> list[RiskPrediction]:
        self._bind_tenant()
        assert self.repository is not None
        return self.repository.get_all_for_customer(customer_id)
