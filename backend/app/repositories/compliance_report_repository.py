from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.aml_rule import AMLRule
from app.models.customer import Customer
from app.models.customer_risk_assessment_history import (
    CustomerRiskAssessmentHistory,
)
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.transaction_monitoring_result import (
    TransactionMonitoringResult,
)
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


class ComplianceReportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _start_datetime(
        value: date | None,
    ) -> datetime | None:
        if value is None:
            return None

        return datetime.combine(
            value,
            time.min,
            tzinfo=timezone.utc,
        )

    @staticmethod
    def _end_datetime_exclusive(
        value: date | None,
    ) -> datetime | None:
        if value is None:
            return None

        next_day = value + timedelta(days=1)

        return datetime.combine(
            next_day,
            time.min,
            tzinfo=timezone.utc,
        )

    def get_case_rows(
        self,
        filters: ComplianceReportFilters,
    ) -> list[CaseReportRow]:
        statement = (
            select(
                IdentityVerificationCase.created_at,
                IdentityVerificationCase.completed_at,
            )
            .join(
                Customer,
                IdentityVerificationCase.customer_id == Customer.id,
            )
            .outerjoin(
                CustomerRiskProfile,
                CustomerRiskProfile.customer_id == Customer.id,
            )
        )

        start_datetime = self._start_datetime(
            filters.start_date,
        )

        end_datetime = self._end_datetime_exclusive(
            filters.end_date,
        )

        if start_datetime is not None:
            statement = statement.where(
                IdentityVerificationCase.created_at >= start_datetime,
            )

        if end_datetime is not None:
            statement = statement.where(
                IdentityVerificationCase.created_at < end_datetime,
            )

        if filters.country is not None:
            statement = statement.where(
                Customer.country_of_residence == filters.country,
            )

        if filters.risk_level is not None:
            statement = statement.where(
                CustomerRiskProfile.risk_level == filters.risk_level,
            )

        rows = self.db.execute(statement).all()

        return [
            CaseReportRow(
                created_at=row.created_at,
                completed_at=row.completed_at,
            )
            for row in rows
        ]

    def get_alert_rows(
        self,
        filters: ComplianceReportFilters,
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
            .join(
                AMLRule,
                TransactionMonitoringResult.rule_id == AMLRule.id,
            )
            .join(
                Customer,
                TransactionMonitoringResult.customer_id == Customer.id,
            )
            .outerjoin(
                CustomerRiskProfile,
                CustomerRiskProfile.customer_id == Customer.id,
            )
            .where(
                TransactionMonitoringResult.result
                == TransactionMonitoringOutcome.MATCHED,
            )
        )

        start_datetime = self._start_datetime(
            filters.start_date,
        )

        end_datetime = self._end_datetime_exclusive(
            filters.end_date,
        )

        if start_datetime is not None:
            statement = statement.where(
                TransactionMonitoringResult.created_at >= start_datetime,
            )

        if end_datetime is not None:
            statement = statement.where(
                TransactionMonitoringResult.created_at < end_datetime,
            )

        if filters.country is not None:
            statement = statement.where(
                TransactionMonitoringResult.country == filters.country,
            )

        if filters.risk_level is not None:
            statement = statement.where(
                CustomerRiskProfile.risk_level == filters.risk_level,
            )

        statement = statement.order_by(
            TransactionMonitoringResult.created_at.desc(),
        )

        rows = self.db.execute(statement).all()

        return [
            AMLAlertReportRow(
                rule_id=row.rule_id,
                rule_name=row.name,
                severity=row.severity,
                created_at=row.created_at,
                country=row.country,
                risk_level=row.risk_level,
            )
            for row in rows
        ]

    def get_current_risk_rows(
        self,
        filters: ComplianceReportFilters,
    ) -> list[CurrentRiskReportRow]:
        statement = select(
            CustomerRiskProfile.customer_id,
            CustomerRiskProfile.risk_level,
            CustomerRiskProfile.assessed_at,
            Customer.country_of_residence,
        ).join(
            Customer,
            CustomerRiskProfile.customer_id == Customer.id,
        )

        start_datetime = self._start_datetime(
            filters.start_date,
        )

        end_datetime = self._end_datetime_exclusive(
            filters.end_date,
        )

        if start_datetime is not None:
            statement = statement.where(
                CustomerRiskProfile.assessed_at >= start_datetime,
            )

        if end_datetime is not None:
            statement = statement.where(
                CustomerRiskProfile.assessed_at < end_datetime,
            )

        if filters.country is not None:
            statement = statement.where(
                Customer.country_of_residence == filters.country,
            )

        if filters.risk_level is not None:
            statement = statement.where(
                CustomerRiskProfile.risk_level == filters.risk_level,
            )

        rows = self.db.execute(statement).all()

        return [
            CurrentRiskReportRow(
                customer_id=row.customer_id,
                risk_level=row.risk_level,
                assessed_at=row.assessed_at,
                country=row.country_of_residence,
            )
            for row in rows
        ]

    def get_risk_history_rows(
        self,
        filters: ComplianceReportFilters,
    ) -> list[RiskHistoryReportRow]:
        statement = (
            select(
                CustomerRiskAssessmentHistory.customer_id,
                CustomerRiskAssessmentHistory.risk_level,
                CustomerRiskAssessmentHistory.assessed_at,
                Customer.country_of_residence,
            )
            .join(
                Customer,
                CustomerRiskAssessmentHistory.customer_id == Customer.id,
            )
            .order_by(
                CustomerRiskAssessmentHistory.customer_id.asc(),
                CustomerRiskAssessmentHistory.assessed_at.asc(),
            )
        )

        if filters.country is not None:
            statement = statement.where(
                Customer.country_of_residence == filters.country,
            )

        rows = self.db.execute(statement).all()

        result = [
            RiskHistoryReportRow(
                customer_id=row.customer_id,
                risk_level=row.risk_level,
                assessed_at=row.assessed_at,
                country=row.country_of_residence,
            )
            for row in rows
        ]

        if filters.risk_level is not None:
            result = [row for row in result if row.risk_level == filters.risk_level]

        return result
