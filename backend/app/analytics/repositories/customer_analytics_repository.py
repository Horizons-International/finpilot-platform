from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.models.customer_daily import (
    CustomerAnalyticsDaily,
)
from app.models.customer import Customer
from app.models.verification_case import IdentityVerificationCase
from app.models.workflow import Workflow, WorkflowExecution
from app.services.customer_onboarding import (
    CUSTOMER_ONBOARDING_ENTITY_TYPE,
    CUSTOMER_ONBOARDING_WORKFLOW_NAME,
)
from app.utils.enums import (
    CustomerStatus,
    VerificationStatus,
    WorkflowExecutionStatus,
)


class CustomerAnalyticsRepository:
    """Database operations for customer analytics."""

    ACTIVE_CUSTOMER_STATUSES = (
        CustomerStatus.NEW,
        CustomerStatus.PENDING_VERIFICATION,
        CustomerStatus.VERIFIED,
    )

    INACTIVE_CUSTOMER_STATUSES = (
        CustomerStatus.SUSPENDED,
        CustomerStatus.REJECTED,
    )

    COMPLETED_VERIFICATION_STATUSES = (
        VerificationStatus.APPROVED,
        VerificationStatus.REJECTED,
    )

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _start_datetime(value: date) -> datetime:
        return datetime.combine(
            value,
            time.min,
            tzinfo=timezone.utc,
        )

    @staticmethod
    def _end_datetime_exclusive(value: date) -> datetime:
        return datetime.combine(
            value + timedelta(days=1),
            time.min,
            tzinfo=timezone.utc,
        )

    @staticmethod
    def _customer_filters(
        *,
        country: str | None,
        status: CustomerStatus | None,
        end_datetime: datetime,
    ) -> list:
        filters = [
            Customer.created_at < end_datetime,
        ]

        if country is not None:
            filters.append(
                Customer.country_of_residence == country,
            )

        if status is not None:
            filters.append(
                Customer.status == status,
            )

        return filters

    def get_daily_snapshots(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[CustomerAnalyticsDaily]:
        statement = (
            select(CustomerAnalyticsDaily)
            .where(
                CustomerAnalyticsDaily.snapshot_date >= start_date,
                CustomerAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(
                CustomerAnalyticsDaily.snapshot_date,
            )
        )

        return list(
            self.db.scalars(statement).all(),
        )

    def get_latest_snapshot(
        self,
        *,
        end_date: date,
    ) -> CustomerAnalyticsDaily | None:
        statement = (
            select(CustomerAnalyticsDaily)
            .where(
                CustomerAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(
                CustomerAnalyticsDaily.snapshot_date.desc(),
            )
            .limit(1)
        )

        return self.db.scalars(statement).first()

    def get_customer_population_metrics(
        self,
        *,
        end_date: date,
        country: str | None,
        status: CustomerStatus | None,
    ) -> tuple[int, int, int]:
        end_datetime = self._end_datetime_exclusive(
            end_date,
        )

        filters = self._customer_filters(
            country=country,
            status=status,
            end_datetime=end_datetime,
        )

        statement = select(
            func.count(Customer.id).label(
                "total_customers",
            ),
            func.count(Customer.id)
            .filter(
                Customer.status.in_(
                    self.ACTIVE_CUSTOMER_STATUSES,
                ),
            )
            .label(
                "active_customers",
            ),
            func.count(Customer.id)
            .filter(
                Customer.status.in_(
                    self.INACTIVE_CUSTOMER_STATUSES,
                ),
            )
            .label(
                "inactive_customers",
            ),
        ).where(*filters)

        row = self.db.execute(statement).one()

        return (
            int(row._mapping["total_customers"] or 0),
            int(row._mapping["active_customers"] or 0),
            int(row._mapping["inactive_customers"] or 0),
        )

    def get_new_customer_trend(
        self,
        *,
        start_date: date,
        end_date: date,
        country: str | None,
        status: CustomerStatus | None,
    ) -> list[tuple[date, int]]:
        start_datetime = self._start_datetime(
            start_date,
        )

        end_datetime = self._end_datetime_exclusive(
            end_date,
        )

        snapshot_date = func.date(
            func.timezone(
                "UTC",
                Customer.created_at,
            )
        ).label(
            "snapshot_date",
        )

        filters = [
            Customer.created_at >= start_datetime,
            Customer.created_at < end_datetime,
        ]

        if country is not None:
            filters.append(
                Customer.country_of_residence == country,
            )

        if status is not None:
            filters.append(
                Customer.status == status,
            )

        statement = (
            select(
                snapshot_date,
                func.count(Customer.id).label(
                    "customer_count",
                ),
            )
            .where(*filters)
            .group_by(snapshot_date)
            .order_by(snapshot_date)
        )

        result = self.db.execute(statement)

        return [
            (
                row._mapping["snapshot_date"],
                int(row._mapping["customer_count"] or 0),
            )
            for row in result
        ]

    def get_customers_by_country(
        self,
        *,
        end_date: date,
        country: str | None,
        status: CustomerStatus | None,
    ) -> list[tuple[str, int]]:
        end_datetime = self._end_datetime_exclusive(
            end_date,
        )

        filters = self._customer_filters(
            country=country,
            status=status,
            end_datetime=end_datetime,
        )

        normalized_country = func.coalesce(
            Customer.country_of_residence,
            "Unknown",
        ).label(
            "country",
        )

        statement = (
            select(
                normalized_country,
                func.count(Customer.id).label(
                    "customer_count",
                ),
            )
            .where(*filters)
            .group_by(normalized_country)
            .order_by(
                func.count(Customer.id).desc(),
                normalized_country,
            )
        )

        result = self.db.execute(statement)

        return [
            (
                str(row._mapping["country"]),
                int(row._mapping["customer_count"] or 0),
            )
            for row in result
        ]

    def get_customers_by_verification_status(
        self,
        *,
        end_date: date,
        country: str | None,
        status: CustomerStatus | None,
    ) -> list[tuple[str, int]]:
        end_datetime = self._end_datetime_exclusive(
            end_date,
        )

        customer_filters = self._customer_filters(
            country=country,
            status=status,
            end_datetime=end_datetime,
        )

        latest_case_number = (
            func.row_number()
            .over(
                partition_by=IdentityVerificationCase.customer_id,
                order_by=IdentityVerificationCase.created_at.desc(),
            )
            .label(
                "row_number",
            )
        )

        latest_cases = (
            select(
                IdentityVerificationCase.customer_id.label(
                    "customer_id",
                ),
                IdentityVerificationCase.status.label(
                    "verification_status",
                ),
                latest_case_number,
            )
            .join(
                Customer,
                IdentityVerificationCase.customer_id == Customer.id,
            )
            .where(
                *customer_filters,
                IdentityVerificationCase.created_at < end_datetime,
            )
            .subquery()
        )

        statement = (
            select(
                latest_cases.c.verification_status,
                func.count(latest_cases.c.customer_id).label(
                    "customer_count",
                ),
            )
            .where(
                latest_cases.c.row_number == 1,
            )
            .group_by(
                latest_cases.c.verification_status,
            )
            .order_by(
                func.count(latest_cases.c.customer_id).desc(),
            )
        )

        result = self.db.execute(statement)

        counts = [
            (
                row._mapping["verification_status"].value,
                int(row._mapping["customer_count"] or 0),
            )
            for row in result
        ]

        total_customers = self.get_customer_population_metrics(
            end_date=end_date,
            country=country,
            status=status,
        )[0]

        customers_with_verification = sum(count for _, count in counts)

        customers_without_verification = total_customers - customers_with_verification

        if customers_without_verification > 0:
            counts.append(
                (
                    "NO_VERIFICATION_CASE",
                    customers_without_verification,
                )
            )

        return counts

    def get_verification_lifecycle_metrics(
        self,
        *,
        start_date: date,
        end_date: date,
        country: str | None,
        status: CustomerStatus | None,
    ) -> tuple[int, int, int, int]:
        start_datetime = self._start_datetime(
            start_date,
        )

        end_datetime = self._end_datetime_exclusive(
            end_date,
        )

        customer_filters = []

        if country is not None:
            customer_filters.append(
                Customer.country_of_residence == country,
            )

        if status is not None:
            customer_filters.append(
                Customer.status == status,
            )

        statement = select(
            func.count(IdentityVerificationCase.id)
            .filter(
                IdentityVerificationCase.created_at >= start_datetime,
                IdentityVerificationCase.created_at < end_datetime,
            )
            .label(
                "cases_created",
            ),
            func.count(IdentityVerificationCase.id)
            .filter(
                IdentityVerificationCase.created_at >= start_datetime,
                IdentityVerificationCase.created_at < end_datetime,
                IdentityVerificationCase.completed_at.is_not(None),
                IdentityVerificationCase.completed_at < end_datetime,
                IdentityVerificationCase.status.in_(
                    self.COMPLETED_VERIFICATION_STATUSES,
                ),
            )
            .label(
                "cases_completed",
            ),
            func.count(IdentityVerificationCase.id)
            .filter(
                IdentityVerificationCase.created_at >= start_datetime,
                IdentityVerificationCase.created_at < end_datetime,
                IdentityVerificationCase.completed_at.is_not(None),
                IdentityVerificationCase.completed_at < end_datetime,
                IdentityVerificationCase.status == VerificationStatus.REJECTED,
            )
            .label(
                "cases_rejected",
            ),
        ).join(
            Customer,
            IdentityVerificationCase.customer_id == Customer.id,
        )

        if customer_filters:
            statement = statement.where(
                *customer_filters,
            )

        row = self.db.execute(statement).one()

        pending_filters = [
            Customer.created_at < end_datetime,
            Customer.status == CustomerStatus.PENDING_VERIFICATION,
        ]

        if country is not None:
            pending_filters.append(
                Customer.country_of_residence == country,
            )

        if status is not None:
            pending_filters.append(
                Customer.status == status,
            )

        pending_statement = select(
            func.count(Customer.id),
        ).where(
            *pending_filters,
        )

        pending_count = int(
            self.db.scalar(pending_statement) or 0,
        )

        return (
            int(row._mapping["cases_created"] or 0),
            int(row._mapping["cases_completed"] or 0),
            int(row._mapping["cases_rejected"] or 0),
            pending_count,
        )

    def get_average_onboarding_completion_time_hours(
        self,
        *,
        start_date: date,
        end_date: date,
        country: str | None,
        status: CustomerStatus | None,
    ) -> float | None:
        start_datetime = self._start_datetime(
            start_date,
        )

        end_datetime = self._end_datetime_exclusive(
            end_date,
        )

        customer_filters = []

        if country is not None:
            customer_filters.append(
                Customer.country_of_residence == country,
            )

        if status is not None:
            customer_filters.append(
                Customer.status == status,
            )

        statement = (
            select(
                func.avg(
                    func.extract(
                        "epoch",
                        WorkflowExecution.completed_at - WorkflowExecution.started_at,
                    )
                )
            )
            .select_from(WorkflowExecution)
            .join(
                Workflow,
                WorkflowExecution.workflow_id == Workflow.id,
            )
            .join(
                Customer,
                WorkflowExecution.entity_id == Customer.id,
            )
            .where(
                Workflow.name == CUSTOMER_ONBOARDING_WORKFLOW_NAME,
                func.lower(
                    WorkflowExecution.entity_type,
                )
                == CUSTOMER_ONBOARDING_ENTITY_TYPE.lower(),
                WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
                WorkflowExecution.completed_at >= start_datetime,
                WorkflowExecution.completed_at < end_datetime,
                WorkflowExecution.completed_at.is_not(None),
                *customer_filters,
            )
        )

        average_seconds = self.db.scalar(statement)

        if average_seconds is None:
            return None

        return round(
            float(average_seconds) / 3600,
            2,
        )
