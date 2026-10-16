import pytest

from app.services.case_priority_service import (
    calculate_priority_score,
    priority_level_for_score,
)
from app.utils.enums import ComplianceCasePriority


def test_priority_score_uses_available_weighted_signals():
    score = calculate_priority_score(
        {
            "alert_severity": 90,
            "customer_risk": 80,
            "transaction_risk": 70,
            "transaction_amount": None,
            "previous_history": 40,
            "geographic_risk": None,
        }
    )
    assert score == pytest.approx(
        (90 * 0.25 + 80 * 0.20 + 70 * 0.25 + 40 * 0.10) / 0.80
    )


def test_priority_levels_use_configured_score_bands():
    assert priority_level_for_score(20) == ComplianceCasePriority.LOW
    assert priority_level_for_score(40) == ComplianceCasePriority.MEDIUM
    assert priority_level_for_score(65) == ComplianceCasePriority.HIGH
    assert priority_level_for_score(85) == ComplianceCasePriority.CRITICAL
