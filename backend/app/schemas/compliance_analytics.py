from datetime import date, datetime

from pydantic import BaseModel


class ComplianceAnalyticsFilters(BaseModel):
    start_date: date
    end_date: date


class RiskDistributionPoint(BaseModel):
    snapshot_date: date
    ending_low_risk_customers: int
    ending_medium_risk_customers: int
    ending_high_risk_customers: int
    ending_critical_risk_customers: int


class RiskDistribution(BaseModel):
    ending_low_risk_customers: int
    ending_medium_risk_customers: int
    ending_high_risk_customers: int
    ending_critical_risk_customers: int
    trend: list[RiskDistributionPoint]


class AMLAlertTrendPoint(BaseModel):
    snapshot_date: date
    alerts_created_during_day: int
    ending_total_alerts: int
    ending_low_severity_alerts: int
    ending_medium_severity_alerts: int
    ending_high_severity_alerts: int
    ending_critical_severity_alerts: int


class AMLAlertTrend(BaseModel):
    total_alerts_created_during_period: int
    ending_total_alerts: int
    trend: list[AMLAlertTrendPoint]


class CaseResolutionPoint(BaseModel):
    snapshot_date: date
    cases_created_during_day: int
    cases_closed_during_day: int
    average_resolution_time_hours: float | None


class CaseResolutionPerformance(BaseModel):
    total_cases_created_during_period: int
    total_cases_closed_during_period: int
    ending_open_cases: int
    average_resolution_time_hours: float | None
    trend: list[CaseResolutionPoint]


class VerificationRejectionReason(BaseModel):
    reason: str
    count: int


class VerificationRejectionReport(BaseModel):
    total_rejections: int
    rejection_reasons: list[VerificationRejectionReason]


class ComplianceAnalyticsResponse(BaseModel):
    generated_at: datetime
    filters: ComplianceAnalyticsFilters
    risk_distribution: RiskDistribution
    aml_alert_trends: AMLAlertTrend
    case_resolution_performance: CaseResolutionPerformance
    verification_rejection_reasons: VerificationRejectionReport
