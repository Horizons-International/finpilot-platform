"""Async compliance-report queries with explicit tenant predicates."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aml_rule import AMLRule
from app.models.customer import Customer
from app.models.customer_risk_assessment_history import CustomerRiskAssessmentHistory
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.transaction_monitoring_result import TransactionMonitoringResult
from app.models.verification_case import IdentityVerificationCase
from app.schemas.compliance_reports import ComplianceReportFilters
from app.utils.enums import (
    AMLRuleSeverity,
    CustomerRiskLevel,
    TransactionMonitoringOutcome,
)


@dataclass(frozen=True)
class CaseReportRow:
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True)
class AMLAlertReportRow:
    rule_id: UUID
    rule_name: str
    severity: AMLRuleSeverity
    created_at: datetime
    country: str | None
    risk_level: CustomerRiskLevel | None


@dataclass(frozen=True)
class CurrentRiskReportRow:
    customer_id: UUID
    risk_level: CustomerRiskLevel
    assessed_at: datetime
    country: str | None


@dataclass(frozen=True)
class RiskHistoryReportRow:
    customer_id: UUID
    risk_level: CustomerRiskLevel
    assessed_at: datetime
    country: str | None


class AsyncComplianceReportRepository:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant = db.info.get("tenant_id")
        if active_tenant is not None and active_tenant != tenant_id:
            raise ValueError(
                "Compliance report repository tenant does not match session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    @staticmethod
    def _start_datetime(value: date | None) -> datetime | None:
        return datetime.combine(value, time.min, tzinfo=timezone.utc) if value else None

    @staticmethod
    def _end_datetime_exclusive(value: date | None) -> datetime | None:
        return (
            datetime.combine(value + timedelta(days=1), time.min, tzinfo=timezone.utc)
            if value
            else None
        )

    async def get_case_rows(
        self, filters: ComplianceReportFilters
    ) -> list[CaseReportRow]:
        statement = (
            select(
                IdentityVerificationCase.created_at,
                IdentityVerificationCase.completed_at,
            )
            .join(Customer, IdentityVerificationCase.customer_id == Customer.id)
            .outerjoin(
                CustomerRiskProfile,
                and_(
                    CustomerRiskProfile.customer_id == Customer.id,
                    CustomerRiskProfile.tenant_id == self.tenant_id,
                ),
            )
            .where(
                IdentityVerificationCase.tenant_id == self.tenant_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        start = self._start_datetime(filters.start_date)
        end = self._end_datetime_exclusive(filters.end_date)
        if start is not None:
            statement = statement.where(IdentityVerificationCase.created_at >= start)
        if end is not None:
            statement = statement.where(IdentityVerificationCase.created_at < end)
        if filters.country is not None:
            statement = statement.where(
                Customer.country_of_residence == filters.country
            )
        if filters.risk_level is not None:
            statement = statement.where(
                CustomerRiskProfile.risk_level == filters.risk_level
            )
        rows = (await self.db.execute(statement)).all()
        return [CaseReportRow(row.created_at, row.completed_at) for row in rows]

    async def get_alert_rows(
        self, filters: ComplianceReportFilters
    ) -> list[AMLAlertReportRow]:
        statement = (
            select(
                TransactionMonitoringResult.rule_id,
                AMLRule.name,
                AMLRule.severity,
                TransactionMonitoringResult.created_at,
                TransactionMonitoringResult.country,
                CustomerRiskProfile.risk_level,
            )
            .join(AMLRule, TransactionMonitoringResult.rule_id == AMLRule.id)
            .join(Customer, TransactionMonitoringResult.customer_id == Customer.id)
            .outerjoin(
                CustomerRiskProfile,
                and_(
                    CustomerRiskProfile.customer_id == Customer.id,
                    CustomerRiskProfile.tenant_id == self.tenant_id,
                ),
            )
            .where(
                TransactionMonitoringResult.result
                == TransactionMonitoringOutcome.MATCHED,
                TransactionMonitoringResult.tenant_id == self.tenant_id,
                AMLRule.tenant_id == self.tenant_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        start = self._start_datetime(filters.start_date)
        end = self._end_datetime_exclusive(filters.end_date)
        if start is not None:
            statement = statement.where(TransactionMonitoringResult.created_at >= start)
        if end is not None:
            statement = statement.where(TransactionMonitoringResult.created_at < end)
        if filters.country is not None:
            statement = statement.where(
                TransactionMonitoringResult.country == filters.country
            )
        if filters.risk_level is not None:
            statement = statement.where(
                CustomerRiskProfile.risk_level == filters.risk_level
            )
        rows = (
            await self.db.execute(
                statement.order_by(TransactionMonitoringResult.created_at.desc())
            )
        ).all()
        return [
            AMLAlertReportRow(
                row.rule_id,
                row.name,
                row.severity,
                row.created_at,
                row.country,
                row.risk_level,
            )
            for row in rows
        ]

    async def get_current_risk_rows(
        self, filters: ComplianceReportFilters
    ) -> list[CurrentRiskReportRow]:
        statement = (
            select(
                CustomerRiskProfile.customer_id,
                CustomerRiskProfile.risk_level,
                CustomerRiskProfile.assessed_at,
                Customer.country_of_residence,
            )
            .join(Customer, CustomerRiskProfile.customer_id == Customer.id)
            .where(
                CustomerRiskProfile.tenant_id == self.tenant_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        start = self._start_datetime(filters.start_date)
        end = self._end_datetime_exclusive(filters.end_date)
        if start is not None:
            statement = statement.where(CustomerRiskProfile.assessed_at >= start)
        if end is not None:
            statement = statement.where(CustomerRiskProfile.assessed_at < end)
        if filters.country is not None:
            statement = statement.where(
                Customer.country_of_residence == filters.country
            )
        if filters.risk_level is not None:
            statement = statement.where(
                CustomerRiskProfile.risk_level == filters.risk_level
            )
        rows = (await self.db.execute(statement)).all()
        return [
            CurrentRiskReportRow(
                row.customer_id,
                row.risk_level,
                row.assessed_at,
                row.country_of_residence,
            )
            for row in rows
        ]

    async def get_risk_history_rows(
        self, filters: ComplianceReportFilters
    ) -> list[RiskHistoryReportRow]:
        statement = (
            select(
                CustomerRiskAssessmentHistory.customer_id,
                CustomerRiskAssessmentHistory.risk_level,
                CustomerRiskAssessmentHistory.assessed_at,
                Customer.country_of_residence,
            )
            .join(Customer, CustomerRiskAssessmentHistory.customer_id == Customer.id)
            .where(
                CustomerRiskAssessmentHistory.tenant_id == self.tenant_id,
                Customer.tenant_id == self.tenant_id,
            )
            .order_by(
                CustomerRiskAssessmentHistory.customer_id.asc(),
                CustomerRiskAssessmentHistory.assessed_at.asc(),
            )
        )
        if filters.country is not None:
            statement = statement.where(
                Customer.country_of_residence == filters.country
            )
        rows = (await self.db.execute(statement)).all()
        results = [
            RiskHistoryReportRow(
                row.customer_id,
                row.risk_level,
                row.assessed_at,
                row.country_of_residence,
            )
            for row in rows
        ]
        if filters.risk_level is not None:
            results = [row for row in results if row.risk_level == filters.risk_level]
        return results
