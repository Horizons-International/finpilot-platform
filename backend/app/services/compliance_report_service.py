from collections import defaultdict
from datetime import date
from typing import DefaultDict

from sqlalchemy.orm import Session

from app.repositories.compliance_report_repository import (
    ComplianceReportRepository,
    CurrentRiskReportRow,
    RiskHistoryReportRow,
)
from app.schemas.compliance_reports import (
    AMLAlertRuleCount,
    AMLAlertSeverityCount,
    AMLAlertsReportResponse,
    AMLAlertStatusCount,
    ComplianceCasesReportResponse,
    ComplianceReportFilters,
    CustomerRiskChange,
    CustomerRiskLevelCount,
    CustomerRiskReportResponse,
)
from app.utils.enums import (
    AMLRuleSeverity,
    CustomerRiskLevel,
)


class ComplianceReportService:
    ALERT_STATUS_OPEN = "OPEN"

    def __init__(self, db: Session) -> None:
        self.repository = ComplianceReportRepository(db)

    def get_compliance_cases_report(
        self,
        filters: ComplianceReportFilters,
    ) -> ComplianceCasesReportResponse:
        rows = self.repository.get_case_rows(filters)

        total_cases = len(rows)

        closed_cases = sum(1 for row in rows if row.completed_at is not None)

        open_cases = total_cases - closed_cases

        resolution_times: list[float] = []

        for row in rows:
            if row.completed_at is None:
                continue

            duration_seconds = (row.completed_at - row.created_at).total_seconds()

            if duration_seconds >= 0:
                resolution_times.append(
                    duration_seconds / 3600,
                )

        average_resolution_time_hours = (
            round(
                sum(resolution_times) / len(resolution_times),
                2,
            )
            if resolution_times
            else None
        )

        return ComplianceCasesReportResponse(
            total_cases=total_cases,
            open_cases=open_cases,
            closed_cases=closed_cases,
            average_resolution_time_hours=(average_resolution_time_hours),
        )

    def get_aml_alerts_report(
        self,
        filters: ComplianceReportFilters,
    ) -> AMLAlertsReportResponse:
        rows = self.repository.get_alert_rows(filters)

        severity_counts: DefaultDict[
            AMLRuleSeverity,
            int,
        ] = defaultdict(int)

        rule_counts: DefaultDict[
            tuple,
            int,
        ] = defaultdict(int)

        for row in rows:
            severity_counts[row.severity] += 1

            rule_counts[
                (
                    row.rule_id,
                    row.rule_name,
                    row.severity,
                )
            ] += 1

        alerts_by_severity = [
            AMLAlertSeverityCount(
                severity=severity,
                count=count,
            )
            for severity, count in sorted(
                severity_counts.items(),
                key=lambda item: item[0].value,
            )
        ]

        alerts_by_rule = [
            AMLAlertRuleCount(
                rule_id=rule_id,
                rule_name=rule_name,
                severity=severity,
                count=count,
            )
            for (
                rule_id,
                rule_name,
                severity,
            ), count in sorted(
                rule_counts.items(),
                key=lambda item: (
                    -item[1],
                    item[0][1],
                ),
            )
        ]

        alert_status = []

        if rows:
            alert_status.append(
                AMLAlertStatusCount(
                    status=self.ALERT_STATUS_OPEN,
                    count=len(rows),
                )
            )

        return AMLAlertsReportResponse(
            total_alerts=len(rows),
            alerts_by_severity=alerts_by_severity,
            alerts_by_rule=alerts_by_rule,
            alert_status=alert_status,
        )

    def get_customer_risk_report(
        self,
        filters: ComplianceReportFilters,
    ) -> CustomerRiskReportResponse:
        current_rows: list[CurrentRiskReportRow] = (
            self.repository.get_current_risk_rows(filters)
        )

        risk_counts: DefaultDict[
            CustomerRiskLevel,
            int,
        ] = defaultdict(int)

        for current_row in current_rows:
            risk_counts[current_row.risk_level] += 1

        customers_by_risk_level = [
            CustomerRiskLevelCount(
                risk_level=risk_level,
                count=count,
            )
            for risk_level, count in sorted(
                risk_counts.items(),
                key=lambda item: item[0].value,
            )
        ]

        high_risk_customers = sum(
            count
            for risk_level, count in risk_counts.items()
            if risk_level
            in {
                CustomerRiskLevel.HIGH,
                CustomerRiskLevel.CRITICAL,
            }
        )

        history_rows: list[RiskHistoryReportRow] = (
            self.repository.get_risk_history_rows(filters)
        )

        change_counts: DefaultDict[
            tuple[
                date,
                CustomerRiskLevel,
                CustomerRiskLevel,
            ],
            int,
        ] = defaultdict(int)

        start_date = filters.start_date
        end_date = filters.end_date

        previous_customer_id = None
        previous_level: CustomerRiskLevel | None = None

        for history_row in history_rows:
            # A new customer starts a new risk-history sequence.
            if history_row.customer_id != previous_customer_id:
                previous_customer_id = history_row.customer_id
                previous_level = history_row.risk_level
                continue

            current_level = history_row.risk_level

            if previous_level != current_level:
                change_date = history_row.assessed_at.date()

                if start_date is not None and change_date < start_date:
                    previous_level = current_level
                    continue

                if end_date is not None and change_date > end_date:
                    previous_level = current_level
                    continue

                # previous_level cannot be None here because
                # the first row for every customer initializes it.
                assert previous_level is not None

                change_counts[
                    (
                        change_date,
                        previous_level,
                        current_level,
                    )
                ] += 1

            previous_level = current_level

        risk_changes_over_time = [
            CustomerRiskChange(
                assessed_date=change_date,
                previous_risk_level=previous_level,
                new_risk_level=new_level,
                count=count,
            )
            for (
                change_date,
                previous_level,
                new_level,
            ), count in sorted(
                change_counts.items(),
                key=lambda item: (
                    item[0][0],
                    item[0][1].value,
                    item[0][2].value,
                ),
            )
        ]

        return CustomerRiskReportResponse(
            customers_by_risk_level=customers_by_risk_level,
            high_risk_customers=high_risk_customers,
            risk_changes_over_time=risk_changes_over_time,
        )
