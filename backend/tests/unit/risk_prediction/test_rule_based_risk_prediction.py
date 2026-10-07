from typing import Any

from app.risk_prediction.feature_schema import (
    RiskPredictionFeatures,
)
from app.risk_prediction.rule_based import (
    RuleBasedRiskPredictionModel,
)


def build_features(
    **overrides,
) -> RiskPredictionFeatures:
    values: dict[str, Any] = {
        "country_of_residence": "Sudan",
        "current_risk_level": None,
        "current_risk_score": None,
        "verification_cases_count": 0,
        "verification_rejections_count": 0,
        "verification_approvals_count": 0,
        "verification_pending_count": 0,
        "compliance_cases_count": 0,
        "compliance_closed_cases_count": 0,
        "aml_alert_count": 0,
        "aml_critical_alert_count": 0,
        "risk_assessments_count": 0,
        "previous_high_risk_assessments": 0,
        "previous_critical_risk_assessments": 0,
        "transaction_monitoring_events": 0,
        "transaction_monitoring_matches": 0,
    }

    values.update(overrides)

    return RiskPredictionFeatures(**values)


def test_rule_based_model_returns_low_probability_for_clean_customer():
    model = RuleBasedRiskPredictionModel()

    result = model.predict(
        build_features(),
    )

    assert result.risk_probability == 0.05


def test_rule_based_model_increases_probability_for_high_risk_customer():
    model = RuleBasedRiskPredictionModel()

    result = model.predict(
        build_features(
            current_risk_level="HIGH",
        ),
    )

    assert result.risk_probability == 0.30


def test_rule_based_model_increases_probability_for_critical_alert():
    model = RuleBasedRiskPredictionModel()

    result = model.predict(
        build_features(
            aml_critical_alert_count=1,
        ),
    )

    assert result.risk_probability == 0.20


def test_rule_based_model_combines_multiple_risk_signals():
    model = RuleBasedRiskPredictionModel()

    result = model.predict(
        build_features(
            current_risk_level="HIGH",
            verification_rejections_count=2,
            compliance_cases_count=3,
            aml_alert_count=3,
            aml_critical_alert_count=1,
            previous_critical_risk_assessments=1,
            transaction_monitoring_matches=3,
        ),
    )

    assert 0 < result.risk_probability <= 1


def test_model_exposes_version():
    model = RuleBasedRiskPredictionModel()

    assert model.version == "rule-based-v1"
