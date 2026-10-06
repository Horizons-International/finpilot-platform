from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.analytics.repositories.compliance_analytics_repository import (
    ComplianceAnalyticsRepository,
)
from app.schemas.compliance_analytics import (
    AMLAlertTrend,
    AMLAlertTrendPoint,
    CaseResolutionPerformance,
    CaseResolutionPoint,
    ComplianceAnalyticsFilters,
    ComplianceAnalyticsResponse,
    RiskDistribution,
    RiskDistributionPoint,
    VerificationRejectionReason,
    VerificationRejectionReport,
)
from app.utils.date_time import utc_now
from app.utils.errors import bad_request


class ComplianceAnalyticsService:
    DEFAULT_LOOKBACK_DAYS = 30
    MAX_LOOKBACK_DAYS = 366

    def __init__(self, db: Session) -> None:
        self.repository = ComplianceAnalyticsRepository(db)

    def get_analytics(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> ComplianceAnalyticsResponse:
        normalized_end_date = end_date or utc_now().date()

        normalized_start_date = start_date or (
            normalized_end_date - timedelta(days=self.DEFAULT_LOOKBACK_DAYS - 1)
        )

        if normalized_start_date > normalized_end_date:
            raise bad_request(
                "start_date cannot be after end_date.",
            )

        lookback_days = (normalized_end_date - normalized_start_date).days + 1

        if lookback_days > self.MAX_LOOKBACK_DAYS:
            raise bad_request(
                "Analytics date range cannot exceed 366 days.",
            )

        snapshots = self.repository.get_daily_snapshots(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        latest_snapshot = self.repository.get_latest_snapshot(
            end_date=normalized_end_date,
        )

        cases_created = self.repository.get_cases_created_by_day(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        cases_closed = self.repository.get_cases_closed_by_day(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        rejection_reasons = self.repository.get_verification_rejection_reasons(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        risk_trend = [
            RiskDistributionPoint(
                snapshot_date=row.snapshot_date,
                ending_low_risk_customers=row.ending_low_risk_customers,
                ending_medium_risk_customers=row.ending_medium_risk_customers,
                ending_high_risk_customers=row.ending_high_risk_customers,
                ending_critical_risk_customers=(row.ending_critical_risk_customers),
            )
            for row in snapshots
        ]

        aml_trend = [
            AMLAlertTrendPoint(
                snapshot_date=row.snapshot_date,
                alerts_created_during_day=row.alerts_created_during_day,
                ending_total_alerts=row.ending_total_alerts,
                ending_low_severity_alerts=(row.ending_low_severity_alerts),
                ending_medium_severity_alerts=(row.ending_medium_severity_alerts),
                ending_high_severity_alerts=(row.ending_high_severity_alerts),
                ending_critical_severity_alerts=(row.ending_critical_severity_alerts),
            )
            for row in snapshots
        ]

        case_resolution_trend: list[CaseResolutionPoint] = []

        current_date = normalized_start_date

        while current_date <= normalized_end_date:
            closed_count, average_resolution_hours = cases_closed.get(
                current_date,
                (0, None),
            )

            case_resolution_trend.append(
                CaseResolutionPoint(
                    snapshot_date=current_date,
                    cases_created_during_day=cases_created.get(
                        current_date,
                        0,
                    ),
                    cases_closed_during_day=closed_count,
                    average_resolution_time_hours=average_resolution_hours,
                )
            )

            current_date += timedelta(days=1)

        total_cases_created = sum(
            cases_created.values(),
        )

        total_cases_closed, overall_average_resolution_hours = (
            self.repository.get_case_resolution_summary(
                start_date=normalized_start_date,
                end_date=normalized_end_date,
            )
        )

        return ComplianceAnalyticsResponse(
            generated_at=utc_now(),
            filters=ComplianceAnalyticsFilters(
                start_date=normalized_start_date,
                end_date=normalized_end_date,
            ),
            risk_distribution=RiskDistribution(
                ending_low_risk_customers=(
                    latest_snapshot.ending_low_risk_customers if latest_snapshot else 0
                ),
                ending_medium_risk_customers=(
                    latest_snapshot.ending_medium_risk_customers
                    if latest_snapshot
                    else 0
                ),
                ending_high_risk_customers=(
                    latest_snapshot.ending_high_risk_customers if latest_snapshot else 0
                ),
                ending_critical_risk_customers=(
                    latest_snapshot.ending_critical_risk_customers
                    if latest_snapshot
                    else 0
                ),
                trend=risk_trend,
            ),
            aml_alert_trends=AMLAlertTrend(
                total_alerts_created_during_period=sum(
                    row.alerts_created_during_day for row in snapshots
                ),
                ending_total_alerts=(
                    latest_snapshot.ending_total_alerts if latest_snapshot else 0
                ),
                trend=aml_trend,
            ),
            case_resolution_performance=CaseResolutionPerformance(
                total_cases_created_during_period=(total_cases_created),
                total_cases_closed_during_period=(total_cases_closed),
                ending_open_cases=(
                    latest_snapshot.ending_open_cases if latest_snapshot else 0
                ),
                average_resolution_time_hours=(overall_average_resolution_hours),
                trend=case_resolution_trend,
            ),
            verification_rejection_reasons=VerificationRejectionReport(
                total_rejections=sum(count for _, count in rejection_reasons),
                rejection_reasons=[
                    VerificationRejectionReason(
                        reason=reason,
                        count=count,
                    )
                    for reason, count in rejection_reasons
                ],
            ),
        )
