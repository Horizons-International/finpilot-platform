from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy.orm import Session

from app.analytics.models.compliance_daily import ComplianceAnalyticsDaily
from app.analytics.models.customer_daily import CustomerAnalyticsDaily
from app.analytics.models.operations_daily import OperationsAnalyticsDaily
from app.analytics.repositories.aggregation_repository import (
    AnalyticsAggregationRepository,
)
from app.analytics.services.snapshot_service import (
    AnalyticsSnapshotService,
)
from app.utils.date_time import utc_now


class AnalyticsAggregationService:
    """Coordinates daily and monthly analytics aggregation."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.snapshot_service = AnalyticsSnapshotService(db)
        self.repository = AnalyticsAggregationRepository(db)

    @staticmethod
    def _end_of_day(
        aggregation_date: date,
    ) -> datetime:
        next_day = aggregation_date + timedelta(days=1)

        return datetime.combine(
            next_day,
            time.min,
            tzinfo=timezone.utc,
        ) - timedelta(microseconds=1)

    @staticmethod
    def _previous_month(
        current_date: date,
    ) -> date:
        first_of_current_month = current_date.replace(day=1)
        previous_month_end = first_of_current_month - timedelta(days=1)

        return previous_month_end.replace(day=1)

    @staticmethod
    def _sum_field(
        rows: Sequence[Any],
        field: str,
    ) -> int:
        return sum(int(getattr(row, field) or 0) for row in rows)

    @staticmethod
    def _validate_complete_month(
        *,
        rows: Sequence[Any],
        month_start: date,
        domain: str,
    ) -> None:
        expected_days = monthrange(
            month_start.year,
            month_start.month,
        )[1]

        if len(rows) != expected_days:
            raise ValueError(
                f"{domain} analytics data is incomplete for "
                f"{month_start.isoformat()}. "
                f"Expected {expected_days} daily rows, "
                f"found {len(rows)}.",
            )

    def aggregate_daily(
        self,
        *,
        aggregation_date: date | None = None,
    ) -> None:
        target_date = (
            aggregation_date
            if aggregation_date is not None
            else utc_now().date() - timedelta(days=1)
        )

        try:
            self.snapshot_service.capture_snapshot(
                as_of=self._end_of_day(target_date),
                commit=False,
            )

            event_metrics = self.repository.collect_daily_event_metrics(
                aggregation_date=target_date,
            )

            self.repository.update_daily_event_metrics(
                aggregation_date=target_date,
                metrics=event_metrics,
            )

            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _aggregate_customer_monthly(
        self,
        *,
        month_start: date,
        rows: list[CustomerAnalyticsDaily],
        captured_at: datetime,
    ) -> None:
        ending_row = rows[-1]

        previous_row = self.repository.get_previous_customer_snapshot(
            month_start=month_start,
        )

        if previous_row is None:
            customer_growth = int(ending_row.ending_total_customers or 0)
        else:
            customer_growth = int(ending_row.ending_total_customers or 0) - int(
                previous_row.ending_total_customers or 0
            )

        self.repository.save_customer_monthly(
            month_start=month_start,
            ending_total_customers=(int(ending_row.ending_total_customers or 0)),
            customers_registered_during_month=self._sum_field(
                rows,
                "customers_registered_during_day",
            ),
            verification_approvals_during_month=self._sum_field(
                rows,
                "verification_approvals_during_day",
            ),
            customer_growth=customer_growth,
            captured_at=captured_at,
        )

    def _aggregate_compliance_monthly(
        self,
        *,
        month_start: date,
        rows: list[ComplianceAnalyticsDaily],
        captured_at: datetime,
    ) -> None:
        ending_row = rows[-1]

        metrics = {
            "ending_total_cases": int(
                ending_row.ending_total_cases or 0,
            ),
            "cases_created_during_month": self._sum_field(
                rows,
                "cases_created_during_day",
            ),
            "ending_open_cases": int(
                ending_row.ending_open_cases or 0,
            ),
            "ending_resolved_cases": int(
                ending_row.ending_resolved_cases or 0,
            ),
            "ending_closed_cases": int(
                ending_row.ending_closed_cases or 0,
            ),
            "ending_total_alerts": int(
                ending_row.ending_total_alerts or 0,
            ),
            "alerts_created_during_month": self._sum_field(
                rows,
                "alerts_created_during_day",
            ),
            "ending_low_risk_customers": int(
                ending_row.ending_low_risk_customers or 0,
            ),
            "ending_medium_risk_customers": int(
                ending_row.ending_medium_risk_customers or 0,
            ),
            "ending_high_risk_customers": int(
                ending_row.ending_high_risk_customers or 0,
            ),
            "ending_critical_risk_customers": int(
                ending_row.ending_critical_risk_customers or 0,
            ),
        }

        self.repository.save_compliance_monthly(
            month_start=month_start,
            metrics=metrics,
            captured_at=captured_at,
        )

    def _aggregate_operations_monthly(
        self,
        *,
        month_start: date,
        rows: list[OperationsAnalyticsDaily],
        captured_at: datetime,
    ) -> None:
        ending_row = rows[-1]

        metrics = {
            "ending_total_tasks": int(
                ending_row.ending_total_tasks or 0,
            ),
            "tasks_created_during_month": self._sum_field(
                rows,
                "tasks_created_during_day",
            ),
            "tasks_completed_during_month": self._sum_field(
                rows,
                "tasks_completed_during_day",
            ),
            "ending_open_tasks": int(
                ending_row.ending_open_tasks or 0,
            ),
            "ending_overdue_tasks": int(
                ending_row.ending_overdue_tasks or 0,
            ),
            "tasks_completed_within_sla_during_month": self._sum_field(
                rows,
                "tasks_completed_within_sla_during_day",
            ),
            "tasks_completed_breached_sla_during_month": self._sum_field(
                rows,
                "tasks_completed_breached_sla_during_day",
            ),
            "ending_total_workflows": int(
                ending_row.ending_total_workflows or 0,
            ),
            "workflows_started_during_month": self._sum_field(
                rows,
                "workflows_started_during_day",
            ),
            "workflows_completed_during_month": self._sum_field(
                rows,
                "workflows_completed_during_day",
            ),
            "workflows_failed_during_month": self._sum_field(
                rows,
                "workflows_failed_during_day",
            ),
            "ending_active_workflows": int(
                ending_row.ending_active_workflows or 0,
            ),
            "workflows_completed_within_sla_during_month": self._sum_field(
                rows,
                "workflows_completed_within_sla_during_day",
            ),
            "workflows_completed_breached_sla_during_month": self._sum_field(
                rows,
                "workflows_completed_breached_sla_during_day",
            ),
        }

        self.repository.save_operations_monthly(
            month_start=month_start,
            metrics=metrics,
            captured_at=captured_at,
        )

    def aggregate_monthly(
        self,
        *,
        month_start: date | None = None,
    ) -> None:
        target_month = (
            month_start
            if month_start is not None
            else self._previous_month(
                utc_now().date(),
            )
        )

        try:
            customer_rows = self.repository.get_customer_daily_rows(
                month_start=target_month,
            )
            compliance_rows = self.repository.get_compliance_daily_rows(
                month_start=target_month,
            )
            operations_rows = self.repository.get_operations_daily_rows(
                month_start=target_month,
            )

            self._validate_complete_month(
                rows=customer_rows,
                month_start=target_month,
                domain="Customer",
            )
            self._validate_complete_month(
                rows=compliance_rows,
                month_start=target_month,
                domain="Compliance",
            )
            self._validate_complete_month(
                rows=operations_rows,
                month_start=target_month,
                domain="Operations",
            )

            captured_at = utc_now()

            self._aggregate_customer_monthly(
                month_start=target_month,
                rows=customer_rows,
                captured_at=captured_at,
            )

            self._aggregate_compliance_monthly(
                month_start=target_month,
                rows=compliance_rows,
                captured_at=captured_at,
            )

            self._aggregate_operations_monthly(
                month_start=target_month,
                rows=operations_rows,
                captured_at=captured_at,
            )

            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
