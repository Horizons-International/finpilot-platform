"""Async tenant-scoped aggregate queries for customer analytics."""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.verification_case import IdentityVerificationCase
from app.models.workflow import Workflow, WorkflowExecution
from app.services.customer_onboarding import (
    CUSTOMER_ONBOARDING_ENTITY_TYPE,
    CUSTOMER_ONBOARDING_WORKFLOW_NAME,
)
from app.utils.enums import CustomerStatus, VerificationStatus, WorkflowExecutionStatus


class AsyncCustomerAnalyticsRepository:
    ACTIVE_CUSTOMER_STATUSES = (
        CustomerStatus.NEW,
        CustomerStatus.PENDING_VERIFICATION,
        CustomerStatus.VERIFIED,
    )
    INACTIVE_CUSTOMER_STATUSES = (CustomerStatus.SUSPENDED, CustomerStatus.REJECTED)
    COMPLETED_VERIFICATION_STATUSES = (
        VerificationStatus.APPROVED,
        VerificationStatus.REJECTED,
    )

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        self.db = db
        active = db.info.get("tenant_id")
        if active is not None and active != tenant_id:
            raise ValueError(
                "Analytics repository tenant does not match session tenant."
            )
        self.tenant_id = tenant_id
        db.info["tenant_id"] = tenant_id

    @staticmethod
    def _start(value: date) -> datetime:
        return datetime.combine(value, time.min, tzinfo=timezone.utc)

    @staticmethod
    def _end(value: date) -> datetime:
        return datetime.combine(
            value + timedelta(days=1), time.min, tzinfo=timezone.utc
        )

    def _customer_filters(
        self,
        *,
        country: str | None,
        status: CustomerStatus | None,
        end_datetime: datetime,
    ) -> list:
        filters = [
            Customer.tenant_id == self.tenant_id,
            Customer.created_at < end_datetime,
        ]
        if country is not None:
            filters.append(Customer.country_of_residence == country)
        if status is not None:
            filters.append(Customer.status == status)
        return filters

    async def get_customer_population_metrics(
        self, *, end_date: date, country: str | None, status: CustomerStatus | None
    ) -> tuple[int, int, int]:
        statement = select(
            func.count(Customer.id).label("total_customers"),
            func.count(Customer.id)
            .filter(Customer.status.in_(self.ACTIVE_CUSTOMER_STATUSES))
            .label("active_customers"),
            func.count(Customer.id)
            .filter(Customer.status.in_(self.INACTIVE_CUSTOMER_STATUSES))
            .label("inactive_customers"),
        ).where(
            *self._customer_filters(
                country=country, status=status, end_datetime=self._end(end_date)
            )
        )
        row = (await self.db.execute(statement)).one()
        return (
            int(row.total_customers or 0),
            int(row.active_customers or 0),
            int(row.inactive_customers or 0),
        )

    async def get_new_customer_trend(
        self,
        *,
        start_date: date,
        end_date: date,
        country: str | None,
        status: CustomerStatus | None,
    ) -> list[tuple[date, int]]:
        snapshot_date = func.date(func.timezone("UTC", Customer.created_at)).label(
            "snapshot_date"
        )
        filters = [
            Customer.tenant_id == self.tenant_id,
            Customer.created_at >= self._start(start_date),
            Customer.created_at < self._end(end_date),
        ]
        if country is not None:
            filters.append(Customer.country_of_residence == country)
        if status is not None:
            filters.append(Customer.status == status)
        statement = (
            select(snapshot_date, func.count(Customer.id).label("customer_count"))
            .where(*filters)
            .group_by(snapshot_date)
            .order_by(snapshot_date)
        )
        rows = (await self.db.execute(statement)).all()
        return [(row.snapshot_date, int(row.customer_count or 0)) for row in rows]

    async def get_customers_by_country(
        self, *, end_date: date, country: str | None, status: CustomerStatus | None
    ) -> list[tuple[str, int]]:
        normalized = func.coalesce(Customer.country_of_residence, "Unknown").label(
            "country"
        )
        statement = (
            select(normalized, func.count(Customer.id).label("customer_count"))
            .where(
                *self._customer_filters(
                    country=country, status=status, end_datetime=self._end(end_date)
                )
            )
            .group_by(normalized)
            .order_by(func.count(Customer.id).desc(), normalized)
        )
        rows = (await self.db.execute(statement)).all()
        return [(str(row.country), int(row.customer_count or 0)) for row in rows]

    async def get_customers_by_verification_status(
        self, *, end_date: date, country: str | None, status: CustomerStatus | None
    ) -> list[tuple[str, int]]:
        end_datetime = self._end(end_date)
        row_number = (
            func.row_number()
            .over(
                partition_by=IdentityVerificationCase.customer_id,
                order_by=IdentityVerificationCase.created_at.desc(),
            )
            .label("row_number")
        )
        customer_filters = self._customer_filters(
            country=country, status=status, end_datetime=end_datetime
        )
        latest = (
            select(
                IdentityVerificationCase.customer_id.label("customer_id"),
                IdentityVerificationCase.status.label("verification_status"),
                row_number,
            )
            .join(Customer, IdentityVerificationCase.customer_id == Customer.id)
            .where(
                *customer_filters,
                IdentityVerificationCase.tenant_id == self.tenant_id,
                IdentityVerificationCase.created_at < end_datetime,
            )
            .subquery()
        )
        stmt = (
            select(
                latest.c.verification_status,
                func.count(latest.c.customer_id).label("customer_count"),
            )
            .where(latest.c.row_number == 1)
            .group_by(latest.c.verification_status)
            .order_by(func.count(latest.c.customer_id).desc())
        )
        rows = (await self.db.execute(stmt)).all()
        counts = [
            (row.verification_status.value, int(row.customer_count or 0))
            for row in rows
        ]
        total = (
            await self.get_customer_population_metrics(
                end_date=end_date, country=country, status=status
            )
        )[0]
        missing = total - sum(count for _, count in counts)
        if missing > 0:
            counts.append(("NO_VERIFICATION_CASE", missing))
        return counts

    async def get_verification_lifecycle_metrics(
        self,
        *,
        start_date: date,
        end_date: date,
        country: str | None,
        status: CustomerStatus | None,
    ) -> tuple[int, int, int, int]:
        start, end = self._start(start_date), self._end(end_date)
        customer_filters = [Customer.tenant_id == self.tenant_id]
        if country is not None:
            customer_filters.append(Customer.country_of_residence == country)
        if status is not None:
            customer_filters.append(Customer.status == status)
        stmt = (
            select(
                func.count(IdentityVerificationCase.id)
                .filter(
                    IdentityVerificationCase.created_at >= start,
                    IdentityVerificationCase.created_at < end,
                )
                .label("cases_created"),
                func.count(IdentityVerificationCase.id)
                .filter(
                    IdentityVerificationCase.created_at >= start,
                    IdentityVerificationCase.created_at < end,
                    IdentityVerificationCase.completed_at.is_not(None),
                    IdentityVerificationCase.completed_at < end,
                    IdentityVerificationCase.status.in_(
                        self.COMPLETED_VERIFICATION_STATUSES
                    ),
                )
                .label("cases_completed"),
                func.count(IdentityVerificationCase.id)
                .filter(
                    IdentityVerificationCase.created_at >= start,
                    IdentityVerificationCase.created_at < end,
                    IdentityVerificationCase.completed_at.is_not(None),
                    IdentityVerificationCase.completed_at < end,
                    IdentityVerificationCase.status == VerificationStatus.REJECTED,
                )
                .label("cases_rejected"),
            )
            .select_from(IdentityVerificationCase)
            .join(Customer, IdentityVerificationCase.customer_id == Customer.id)
            .where(
                IdentityVerificationCase.tenant_id == self.tenant_id, *customer_filters
            )
        )
        row = (await self.db.execute(stmt)).one()
        pending_filters = [
            Customer.tenant_id == self.tenant_id,
            Customer.created_at < end,
            Customer.status == CustomerStatus.PENDING_VERIFICATION,
        ]
        if country is not None:
            pending_filters.append(Customer.country_of_residence == country)
        if status is not None:
            pending_filters.append(Customer.status == status)
        pending = int(
            await self.db.scalar(
                select(func.count(Customer.id)).where(*pending_filters)
            )
            or 0
        )
        return (
            int(row.cases_created or 0),
            int(row.cases_completed or 0),
            int(row.cases_rejected or 0),
            pending,
        )

    async def get_average_onboarding_completion_time_hours(
        self,
        *,
        start_date: date,
        end_date: date,
        country: str | None,
        status: CustomerStatus | None,
    ) -> float | None:
        filters = [Customer.tenant_id == self.tenant_id]
        if country is not None:
            filters.append(Customer.country_of_residence == country)
        if status is not None:
            filters.append(Customer.status == status)
        stmt = (
            select(
                func.avg(
                    func.extract(
                        "epoch",
                        WorkflowExecution.completed_at - WorkflowExecution.started_at,
                    )
                )
            )
            .select_from(WorkflowExecution)
            .join(Workflow, WorkflowExecution.workflow_id == Workflow.id)
            .join(Customer, WorkflowExecution.entity_id == Customer.id)
            .where(
                Workflow.tenant_id == self.tenant_id,
                WorkflowExecution.tenant_id == self.tenant_id,
                Workflow.name == CUSTOMER_ONBOARDING_WORKFLOW_NAME,
                func.lower(WorkflowExecution.entity_type)
                == CUSTOMER_ONBOARDING_ENTITY_TYPE.lower(),
                WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
                WorkflowExecution.completed_at >= self._start(start_date),
                WorkflowExecution.completed_at < self._end(end_date),
                WorkflowExecution.completed_at.is_not(None),
                *filters,
            )
        )
        avg_seconds = await self.db.scalar(stmt)
        return None if avg_seconds is None else round(float(avg_seconds) / 3600, 2)
