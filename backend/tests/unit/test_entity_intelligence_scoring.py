from app.repositories.entity_intelligence_repository import (
    risk_level_for_score,
    shared_recipient_risk_score,
)


def test_risk_level_thresholds() -> None:
    assert risk_level_for_score(0) == "LOW"
    assert risk_level_for_score(39) == "LOW"
    assert risk_level_for_score(40) == "MEDIUM"
    assert risk_level_for_score(69) == "MEDIUM"
    assert risk_level_for_score(70) == "HIGH"
    assert risk_level_for_score(84) == "HIGH"
    assert risk_level_for_score(85) == "CRITICAL"
    assert risk_level_for_score(100) == "CRITICAL"


def test_shared_recipient_score_is_bounded_and_requires_multiple_customers() -> None:
    assert shared_recipient_risk_score(0) == 0
    assert shared_recipient_risk_score(1) == 0
    assert shared_recipient_risk_score(2) == 50
    assert shared_recipient_risk_score(3) == 60
    assert shared_recipient_risk_score(4) == 70
    assert shared_recipient_risk_score(10) == 100
