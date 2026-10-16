"""Unit tests for conservative, deterministic recommendation rules."""

from typing import Any

from app.services.ai_risk_recommendation_service import (
    calculate_deterministic_risk,
    required_review_type_for_score,
    risk_level_for_score,
    suggested_action_for_score,
)


def test_risk_level_thresholds() -> None:
    assert risk_level_for_score(0) == "LOW"
    assert risk_level_for_score(24) == "LOW"
    assert risk_level_for_score(25) == "MEDIUM"
    assert risk_level_for_score(49) == "MEDIUM"
    assert risk_level_for_score(50) == "HIGH"
    assert risk_level_for_score(74) == "HIGH"
    assert risk_level_for_score(75) == "CRITICAL"
    assert risk_level_for_score(100) == "CRITICAL"


def test_review_type_and_action_match_policy_band() -> None:
    assert required_review_type_for_score(10) == "ROUTINE_MONITORING"
    assert required_review_type_for_score(30) == "STANDARD_COMPLIANCE_REVIEW"
    assert required_review_type_for_score(60) == "ENHANCED_DUE_DILIGENCE"
    assert required_review_type_for_score(90) == "URGENT_COMPLIANCE_REVIEW"
    assert "routine monitoring" in suggested_action_for_score(10).lower()
    assert "enhanced review" in suggested_action_for_score(60).lower()
    assert "escalate" in suggested_action_for_score(90).lower()


def test_deterministic_score_respects_profile_and_matched_alerts() -> None:
    snapshot: dict[str, Any] = {
        "customer": {"country_of_residence": "GB"},
        "customer_risk_profile": {"risk_level": "MEDIUM", "risk_score": 50},
        "transaction_analyses": [],
        "aml_alerts": {
            "transaction_anomalies": [],
            "matched_monitoring_results": [{"id": "1"}, {"id": "2"}],
        },
        "verification_results": [],
        "previous_compliance_cases": [],
        "document_analysis_results": [],
    }
    score, factors = calculate_deterministic_risk(snapshot)
    assert score == 65
    assert any("2 matched AML" in factor for factor in factors)


def test_rejected_verification_and_critical_open_case_raise_floor() -> None:
    snapshot: dict[str, Any] = {
        "customer": {},
        "customer_risk_profile": None,
        "transaction_analyses": [],
        "aml_alerts": {"transaction_anomalies": [], "matched_monitoring_results": []},
        "verification_results": [{"status": "REJECTED"}],
        "previous_compliance_cases": [
            {
                "status": "UNDER_REVIEW",
                "priority": "CRITICAL",
                "case_type": "AML_ALERT",
            }
        ],
        "document_analysis_results": [],
    }
    score, factors = calculate_deterministic_risk(snapshot)
    assert score == 85
    assert any("Verification result" in factor for factor in factors)
    assert any("unresolved compliance case" in factor for factor in factors)


def test_empty_evidence_uses_cautious_standard_review_floor() -> None:
    snapshot: dict[str, Any] = {
        "customer": {},
        "customer_risk_profile": None,
        "transaction_analyses": [],
        "aml_alerts": {"transaction_anomalies": [], "matched_monitoring_results": []},
        "verification_results": [],
        "previous_compliance_cases": [],
        "document_analysis_results": [],
    }
    score, factors = calculate_deterministic_risk(snapshot)
    assert score == 25
    assert risk_level_for_score(score) == "MEDIUM"
    assert any("incomplete" in factor.lower() for factor in factors)
