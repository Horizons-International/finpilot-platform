"""Native-async compliance, AML and customer-risk report generation."""

from collections import defaultdict
from datetime import date
from typing import DefaultDict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.async_compliance_report_repository import (
    AsyncComplianceReportRepository,
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
from app.utils.enums import AMLRuleSeverity, CustomerRiskLevel


class AsyncComplianceReportService:
    ALERT_STATUS_OPEN = "OPEN"

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active = db.info.get("tenant_id")
        if active is not None and active != tenant_id:
            raise ValueError("Compliance report tenant does not match session tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.repository = AsyncComplianceReportRepository(db, tenant_id)

    async def get_compliance_cases_report(
        self, filters: ComplianceReportFilters
    ) -> ComplianceCasesReportResponse:
        rows = await self.repository.get_case_rows(filters)
        total = len(rows)
        closed = sum(1 for row in rows if row.completed_at is not None)
        durations = [
            (row.completed_at - row.created_at).total_seconds() / 3600
            for row in rows
            if row.completed_at is not None
            and (row.completed_at - row.created_at).total_seconds() >= 0
        ]
        return ComplianceCasesReportResponse(
            total_cases=total,
            open_cases=total - closed,
            closed_cases=closed,
            average_resolution_time_hours=(
                round(sum(durations) / len(durations), 2) if durations else None
            ),
        )

    async def get_aml_alerts_report(
        self, filters: ComplianceReportFilters
    ) -> AMLAlertsReportResponse:
        rows = await self.repository.get_alert_rows(filters)
        severity_counts: DefaultDict[AMLRuleSeverity, int] = defaultdict(int)
        rule_counts: DefaultDict[tuple[UUID, str, AMLRuleSeverity], int] = defaultdict(
            int
        )
        for row in rows:
            severity_counts[row.severity] += 1
            rule_counts[(row.rule_id, row.rule_name, row.severity)] += 1
        alerts_by_severity = [
            AMLAlertSeverityCount(severity=severity, count=count)
            for severity, count in sorted(
                severity_counts.items(), key=lambda item: item[0].value
            )
        ]
        alerts_by_rule = [
            AMLAlertRuleCount(
                rule_id=rule_id, rule_name=rule_name, severity=severity, count=count
            )
            for (rule_id, rule_name, severity), count in sorted(
                rule_counts.items(), key=lambda item: (-item[1], item[0][1])
            )
        ]
        statuses = (
            [AMLAlertStatusCount(status=self.ALERT_STATUS_OPEN, count=len(rows))]
            if rows
            else []
        )
        return AMLAlertsReportResponse(
            total_alerts=len(rows),
            alerts_by_severity=alerts_by_severity,
            alerts_by_rule=alerts_by_rule,
            alert_status=statuses,
        )

    async def get_customer_risk_report(
        self, filters: ComplianceReportFilters
    ) -> CustomerRiskReportResponse:
        current_rows: list[CurrentRiskReportRow] = (  # fmt: skip
            await self.repository.get_current_risk_rows(filters)
        )
        risk_counts: DefaultDict[CustomerRiskLevel, int] = defaultdict(int)
        for current_row in current_rows:
            risk_counts[current_row.risk_level] += 1
        by_risk = [
            CustomerRiskLevelCount(risk_level=level, count=count)
            for level, count in sorted(
                risk_counts.items(), key=lambda item: item[0].value
            )
        ]
        high_risk = sum(
            count
            for level, count in risk_counts.items()
            if level in {CustomerRiskLevel.HIGH, CustomerRiskLevel.CRITICAL}
        )
        history: list[RiskHistoryReportRow] = (  # fmt: skip
            await self.repository.get_risk_history_rows(filters)
        )
        changes: DefaultDict[tuple[date, CustomerRiskLevel, CustomerRiskLevel], int] = (
            defaultdict(int)
        )
        previous_customer_id = None
        previous_level: CustomerRiskLevel | None = None
        for histry_row in history:
            if histry_row.customer_id != previous_customer_id:
                previous_customer_id = histry_row.customer_id
                previous_level = histry_row.risk_level
                continue
            current_level = histry_row.risk_level
            if previous_level != current_level:
                change_date = histry_row.assessed_at.date()
                if filters.start_date is not None and change_date < filters.start_date:
                    previous_level = current_level
                    continue
                if filters.end_date is not None and change_date > filters.end_date:
                    previous_level = current_level
                    continue
                if previous_level is not None:
                    changes[(change_date, previous_level, current_level)] += 1
            previous_level = current_level
        change_rows = [
            CustomerRiskChange(
                assessed_date=change_date,
                previous_risk_level=old_level,
                new_risk_level=new_level,
                count=count,
            )
            for (change_date, old_level, new_level), count in sorted(
                changes.items(),
                key=lambda item: (item[0][0], item[0][1].value, item[0][2].value),
            )
        ]
        return CustomerRiskReportResponse(
            customers_by_risk_level=by_risk,
            high_risk_customers=high_risk,
            risk_changes_over_time=change_rows,
        )
