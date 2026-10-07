from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RiskPredictionFeatures:
    country_of_residence: str | None

    current_risk_level: str | None
    current_risk_score: int | None

    verification_cases_count: int
    verification_rejections_count: int
    verification_approvals_count: int
    verification_pending_count: int

    compliance_cases_count: int
    compliance_closed_cases_count: int

    aml_alert_count: int
    aml_critical_alert_count: int

    risk_assessments_count: int
    previous_high_risk_assessments: int
    previous_critical_risk_assessments: int

    transaction_monitoring_events: int
    transaction_monitoring_matches: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
