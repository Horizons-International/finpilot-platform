"""Native-async tenant-scoped source measures for configurable metrics."""

from collections.abc import Awaitable, Callable
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

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

Measure = Callable[[datetime, datetime], Awaitable[float | None]]


class AsyncMetricMeasureProvider:
    """Provides reusable measures with source queries restricted to one tenant."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active = db.info.get("tenant_id")
        if active is not None and active != tenant_id:
            raise ValueError("Metric measure tenant does not match the session.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self._measures: dict[str, Measure] = {
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

    async def get(
        self, *, measure: str, start_date: date, end_date: date
    ) -> float | None:
        resolver = self._measures.get(measure)
        if resolver is None:
            raise ValueError(f"Unsupported metric measure: '{measure}'.")
        start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        end = datetime.combine(
            end_date + timedelta(days=1), time.min, tzinfo=timezone.utc
        )
        return await resolver(start, end)

    async def _count(self, statement: Select[int]) -> int:
        return int(await self.db.scalar(statement) or 0)

    async def _customer_registrations(self, start: datetime, end: datetime) -> float:
        return float(
            await self._count(
                select(func.count(Customer.id)).where(
                    Customer.tenant_id == self.tenant_id,
                    Customer.created_at >= start,
                    Customer.created_at < end,
                )
            )
        )

    async def _customer_opening_base(self, start: datetime, _: datetime) -> float:
        return float(
            await self._count(
                select(func.count(Customer.id)).where(
                    Customer.tenant_id == self.tenant_id, Customer.created_at < start
                )
            )
        )

    async def _customers_at_end(self, _: datetime, end: datetime) -> float:
        return float(
            await self._count(
                select(func.count(Customer.id)).where(
                    Customer.tenant_id == self.tenant_id, Customer.created_at < end
                )
            )
        )

    async def _verification_cases_created(
        self, start: datetime, end: datetime
    ) -> float:
        return float(
            await self._count(
                select(func.count(IdentityVerificationCase.id)).where(
                    IdentityVerificationCase.tenant_id == self.tenant_id,
                    IdentityVerificationCase.created_at >= start,
                    IdentityVerificationCase.created_at < end,
                )
            )
        )

    async def _verification_cases_completed(
        self, start: datetime, end: datetime
    ) -> float:
        return float(
            await self._count(
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

    async def _verification_approvals(self, start: datetime, end: datetime) -> float:
        return float(
            await self._count(
                select(func.count(IdentityVerificationCase.id)).where(
                    IdentityVerificationCase.tenant_id == self.tenant_id,
                    IdentityVerificationCase.completed_at >= start,
                    IdentityVerificationCase.completed_at < end,
                    IdentityVerificationCase.status == VerificationStatus.APPROVED,
                )
            )
        )

    async def _average_duration(
        self,
        start: datetime,
        end: datetime,
        *conditions: ColumnElement[bool],
    ) -> float | None:
        statement = select(
            func.avg(
                func.extract(
                    "epoch", ComplianceCase.closed_at - ComplianceCase.created_at
                )
            )
        ).where(
            ComplianceCase.tenant_id == self.tenant_id,
            ComplianceCase.closed_at >= start,
            ComplianceCase.closed_at < end,
            ComplianceCase.closed_at.is_not(None),
            *conditions,
        )
        value = await self.db.scalar(statement)
        return None if value is None else float(value)

    async def _compliance_review_time_seconds(
        self, start: datetime, end: datetime
    ) -> float | None:
        return await self._average_duration(start, end)

    async def _alert_resolution_time_seconds(
        self, start: datetime, end: datetime
    ) -> float | None:
        return await self._average_duration(
            start, end, ComplianceCase.case_type == ComplianceCaseType.AML_ALERT
        )

    async def _high_risk_customers_at_end(self, _: datetime, end: datetime) -> float:
        return float(
            await self._count(
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

    async def _tasks_created(self, start: datetime, end: datetime) -> float:
        return float(
            await self._count(
                select(func.count(Task.id)).where(
                    Task.tenant_id == self.tenant_id,
                    Task.created_at >= start,
                    Task.created_at < end,
                )
            )
        )

    async def _tasks_completed(self, start: datetime, end: datetime) -> float:
        return float(
            await self._count(
                select(func.count(Task.id)).where(
                    Task.tenant_id == self.tenant_id,
                    Task.completed_at >= start,
                    Task.completed_at < end,
                    Task.status == TaskStatus.COMPLETED,
                )
            )
        )

    async def _tasks_completed_within_sla(
        self, start: datetime, end: datetime
    ) -> float:
        return float(
            await self._count(
                select(func.count(Task.id)).where(
                    Task.tenant_id == self.tenant_id,
                    Task.completed_at >= start,
                    Task.completed_at < end,
                    Task.status == TaskStatus.COMPLETED,
                    Task.sla_status == SLAStatus.COMPLETED,
                )
            )
        )
