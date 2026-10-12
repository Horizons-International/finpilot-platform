from datetime import date, datetime, time, timedelta, timezone
from typing import Callable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.tenant_context import resolve_tenant_id
from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.task import Task
from app.models.verification_case import IdentityVerificationCase
from app.utils.enums import (
    ComplianceCaseType,
    CustomerRiskLevel,
    SLAStatus,
    TaskStatus,
    VerificationStatus,
)


class MetricMeasureProvider:
    """Provides reusable measures restricted to one tenant."""

    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        self.db = db
        self.tenant_id = resolve_tenant_id(db, tenant_id)
        self._measures: dict[str, Callable[[datetime, datetime], float | None]] = {
            "customer_registrations": self._customer_registrations,
            "customer_opening_base": self._customer_opening_base,
            "customers_at_end": self._customers_at_end,
            "verification_cases_created": self._verification_cases_created,
            "verification_cases_completed": self._verification_cases_completed,
            "verification_approvals": self._verification_approvals,
            "compliance_review_time_seconds": self._compliance_review_time_seconds,
            "alert_resolution_time_seconds": self._alert_resolution_time_seconds,
            "high_risk_customers_at_end": self._high_risk_customers_at_end,
            "tasks_created": self._tasks_created,
            "tasks_completed": self._tasks_completed,
            "tasks_completed_within_sla": self._tasks_completed_within_sla,
        }

    def get(self, *, measure: str, start_date: date, end_date: date) -> float | None:
        resolver = self._measures.get(measure)
        if resolver is None:
            raise ValueError(f"Unsupported metric measure: '{measure}'.")
        start, end = self._period_bounds(start_date, end_date)
        return resolver(start, end)

    @staticmethod
    def _period_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
        return (
            datetime.combine(start_date, time.min, tzinfo=timezone.utc),
            datetime.combine(
                end_date + timedelta(days=1), time.min, tzinfo=timezone.utc
            ),
        )

    def _count(self, statement) -> int:
        return int(self.db.scalar(statement) or 0)

    def _customer_registrations(self, start: datetime, end: datetime) -> float:
        return float(
            self._count(
                select(func.count(Customer.id)).where(
                    Customer.tenant_id == self.tenant_id,
                    Customer.created_at >= start,
                    Customer.created_at < end,
                )
            )
        )

    def _customer_opening_base(self, start: datetime, _: datetime) -> float:
        return float(
            self._count(
                select(func.count(Customer.id)).where(
                    Customer.tenant_id == self.tenant_id,
                    Customer.created_at < start,
                )
            )
        )

    def _customers_at_end(self, _: datetime, end: datetime) -> float:
        return float(
            self._count(
                select(func.count(Customer.id)).where(
                    Customer.tenant_id == self.tenant_id,
                    Customer.created_at < end,
                )
            )
        )

    def _verification_cases_created(self, start: datetime, end: datetime) -> float:
        return float(
            self._count(
                select(func.count(IdentityVerificationCase.id)).where(
                    IdentityVerificationCase.tenant_id == self.tenant_id,
                    IdentityVerificationCase.created_at >= start,
                    IdentityVerificationCase.created_at < end,
                )
            )
        )

    def _verification_cases_completed(self, start: datetime, end: datetime) -> float:
        return float(
            self._count(
                select(func.count(IdentityVerificationCase.id)).where(
                    IdentityVerificationCase.tenant_id == self.tenant_id,
                    IdentityVerificationCase.completed_at >= start,
                    IdentityVerificationCase.completed_at < end,
                    IdentityVerificationCase.status.in_(
                        (VerificationStatus.APPROVED, VerificationStatus.REJECTED)
                    ),
                )
            )
        )

    def _verification_approvals(self, start: datetime, end: datetime) -> float:
        return float(
            self._count(
                select(func.count(IdentityVerificationCase.id)).where(
                    IdentityVerificationCase.tenant_id == self.tenant_id,
                    IdentityVerificationCase.completed_at >= start,
                    IdentityVerificationCase.completed_at < end,
                    IdentityVerificationCase.status == VerificationStatus.APPROVED,
                )
            )
        )

    def _average_duration(
        self, model, start_field, end_field, start: datetime, end: datetime, *filters
    ) -> float | None:
        conditions = [*filters]
        if hasattr(model, "tenant_id"):
            conditions.append(model.tenant_id == self.tenant_id)
        statement = select(
            func.avg(func.extract("epoch", end_field - start_field))
        ).where(
            end_field >= start,
            end_field < end,
            end_field.is_not(None),
            *conditions,
        )
        value = self.db.scalar(statement)
        return None if value is None else float(value)

    def _compliance_review_time_seconds(
        self, start: datetime, end: datetime
    ) -> float | None:
        return self._average_duration(
            ComplianceCase,
            ComplianceCase.created_at,
            ComplianceCase.closed_at,
            start,
            end,
            ComplianceCase.closed_at.is_not(None),
        )

    def _alert_resolution_time_seconds(
        self, start: datetime, end: datetime
    ) -> float | None:
        return self._average_duration(
            ComplianceCase,
            ComplianceCase.created_at,
            ComplianceCase.closed_at,
            start,
            end,
            ComplianceCase.closed_at.is_not(None),
            ComplianceCase.case_type == ComplianceCaseType.AML_ALERT,
        )

    def _high_risk_customers_at_end(self, _: datetime, end: datetime) -> float:
        return float(
            self._count(
                select(func.count(CustomerRiskProfile.id))
                .join(Customer, Customer.id == CustomerRiskProfile.customer_id)
                .where(
                    Customer.tenant_id == self.tenant_id,
                    CustomerRiskProfile.tenant_id == self.tenant_id,
                    Customer.created_at < end,
                    CustomerRiskProfile.assessed_at < end,
                    CustomerRiskProfile.risk_level.in_(
                        (CustomerRiskLevel.HIGH, CustomerRiskLevel.CRITICAL)
                    ),
                )
            )
        )

    def _tasks_created(self, start: datetime, end: datetime) -> float:
        return float(
            self._count(
                select(func.count(Task.id)).where(
                    Task.tenant_id == self.tenant_id,
                    Task.created_at >= start,
                    Task.created_at < end,
                )
            )
        )

    def _tasks_completed(self, start: datetime, end: datetime) -> float:
        return float(
            self._count(
                select(func.count(Task.id)).where(
                    Task.tenant_id == self.tenant_id,
                    Task.completed_at >= start,
                    Task.completed_at < end,
                    Task.status == TaskStatus.COMPLETED,
                )
            )
        )

    def _tasks_completed_within_sla(self, start: datetime, end: datetime) -> float:
        return float(
            self._count(
                select(func.count(Task.id)).where(
                    Task.tenant_id == self.tenant_id,
                    Task.completed_at >= start,
                    Task.completed_at < end,
                    Task.status == TaskStatus.COMPLETED,
                    Task.sla_status == SLAStatus.COMPLETED,
                )
            )
        )
