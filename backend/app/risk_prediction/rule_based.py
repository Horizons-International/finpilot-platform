from app.risk_prediction.base import (
    RiskPredictionModel,
    RiskPredictionResult,
)
from app.risk_prediction.feature_schema import RiskPredictionFeatures


class RuleBasedRiskPredictionModel:
    VERSION = "rule-based-v1"

    @property
    def version(self) -> str:
        return self.VERSION

    def predict(
        self,
        features: RiskPredictionFeatures,
    ) -> RiskPredictionResult:
        probability = 0.05

        probability += self._risk_level_component(
            features.current_risk_level,
        )

        probability += self._verification_component(
            features=features,
        )

        probability += self._compliance_component(
            features=features,
        )

        probability += self._aml_component(
            features=features,
        )

        probability += self._risk_history_component(
            features=features,
        )

        probability += self._monitoring_component(
            features=features,
        )

        probability = max(
            0.0,
            min(
                1.0,
                probability,
            ),
        )

        return RiskPredictionResult(
            risk_probability=round(
                probability,
                8,
            ),
        )

    @staticmethod
    def _risk_level_component(
        risk_level: str | None,
    ) -> float:
        if risk_level is None:
            return 0.0

        return {
            "LOW": 0.00,
            "MEDIUM": 0.10,
            "HIGH": 0.25,
            "CRITICAL": 0.40,
        }.get(
            risk_level,
            0.0,
        )

    @staticmethod
    def _verification_component(
        *,
        features: RiskPredictionFeatures,
    ) -> float:
        score = 0.0

        if features.verification_rejections_count > 0:
            score += 0.10

        if features.verification_pending_count > 0:
            score += 0.05

        if features.verification_cases_count >= 3:
            score += 0.05

        return score

    @staticmethod
    def _compliance_component(
        *,
        features: RiskPredictionFeatures,
    ) -> float:
        if features.compliance_cases_count == 0:
            return 0.0

        score = 0.08

        if features.compliance_cases_count >= 3:
            score += 0.08

        return score

    @staticmethod
    def _aml_component(
        *,
        features: RiskPredictionFeatures,
    ) -> float:
        score = 0.0

        if features.aml_alert_count > 0:
            score += 0.10

        if features.aml_alert_count >= 3:
            score += 0.10

        if features.aml_critical_alert_count > 0:
            score += 0.15

        return score

    @staticmethod
    def _risk_history_component(
        *,
        features: RiskPredictionFeatures,
    ) -> float:
        score = 0.0

        if features.previous_high_risk_assessments > 0:
            score += 0.10

        if features.previous_critical_risk_assessments > 0:
            score += 0.15

        return score

    @staticmethod
    def _monitoring_component(
        *,
        features: RiskPredictionFeatures,
    ) -> float:
        if features.transaction_monitoring_matches == 0:
            return 0.0

        if features.transaction_monitoring_matches >= 3:
            return 0.15

        return 0.08


# Explicitly document the interface compatibility.
_prediction_model_check: type[RiskPredictionModel] = RuleBasedRiskPredictionModel
