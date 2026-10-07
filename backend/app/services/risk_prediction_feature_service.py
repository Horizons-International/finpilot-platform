from uuid import UUID

from app.repositories.risk_prediction_feature_repository import (
    RiskPredictionFeatureRepository,
)
from app.risk_prediction.feature_schema import (
    RiskPredictionFeatures,
)
from app.utils.errors import not_found


class RiskPredictionFeatureService:
    def __init__(
        self,
        repository: RiskPredictionFeatureRepository,
    ) -> None:
        self.repository = repository

    def build_features(
        self,
        customer_id: UUID,
    ) -> RiskPredictionFeatures:
        customer = self.repository.get_customer(
            customer_id,
        )

        if customer is None:
            raise not_found("Customer")

        risk_profile = self.repository.get_current_risk_profile(
            customer_id,
        )

        verification = self.repository.get_verification_features(
            customer_id,
        )

        compliance = self.repository.get_compliance_features(
            customer_id,
        )

        aml = self.repository.get_aml_features(
            customer_id,
        )

        critical_aml_alerts = self.repository.get_critical_aml_alert_count(
            customer_id,
        )

        risk_history = self.repository.get_risk_history_features(
            customer_id,
        )

        return RiskPredictionFeatures(
            country_of_residence=customer.country_of_residence,
            current_risk_level=(
                risk_profile.risk_level.value if risk_profile is not None else None
            ),
            current_risk_score=(
                risk_profile.risk_score if risk_profile is not None else None
            ),
            verification_cases_count=verification["total"],
            verification_rejections_count=verification["rejected"],
            verification_approvals_count=verification["approved"],
            verification_pending_count=verification["pending"],
            compliance_cases_count=compliance["total"],
            compliance_closed_cases_count=compliance["closed"],
            aml_alert_count=aml["total"],
            aml_critical_alert_count=critical_aml_alerts,
            risk_assessments_count=risk_history["total"],
            previous_high_risk_assessments=risk_history["high"],
            previous_critical_risk_assessments=risk_history["critical"],
            transaction_monitoring_events=aml["total"],
            transaction_monitoring_matches=aml["matches"],
        )
