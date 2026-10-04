from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.models.compliance_daily import ComplianceAnalyticsDaily
from app.analytics.models.compliance_monthly import ComplianceAnalyticsMonthly
from app.analytics.models.customer_daily import CustomerAnalyticsDaily
from app.analytics.models.customer_monthly import CustomerAnalyticsMonthly
from app.analytics.models.operations_daily import OperationsAnalyticsDaily
from app.analytics.models.operations_monthly import OperationsAnalyticsMonthly
from app.models.aml_rule import AMLRule
from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.task import Task
from app.models.transaction_monitoring_result import (
    TransactionMonitoringResult,
)
from app.models.verification_case import IdentityVerificationCase
from app.models.workflow import WorkflowExecution
from app.utils.enums import (
    SLAStatus,
    TaskStatus,
    TransactionMonitoringOutcome,
    VerificationStatus,
    WorkflowExecutionStatus,
)


class AnalyticsAggregationRepository:
    """Database operations for daily event and monthly analytics."""

    CUSTOMER_EVENT_FIELDS = (
        "customers_registered_during_day",
        "verification_approvals_during_day",
    )

    COMPLIANCE_EVENT_FIELDS = (
        "cases_created_during_day",
        "alerts_created_during_day",
    )

    OPERATIONS_EVENT_FIELDS = (
        "tasks_created_during_day",
        "tasks_completed_during_day",
        "tasks_completed_within_sla_during_day",
        "tasks_completed_breached_sla_during_day",
        "workflows_started_during_day",
        "workflows_completed_during_day",
        "workflows_failed_during_day",
        "workflows_completed_within_sla_during_day",
        "workflows_completed_breached_sla_during_day",
    )

    CUSTOMER_MONTHLY_FIELDS = (
        "ending_total_customers",
        "customers_registered_during_month",
        "verification_approvals_during_month",
        "customer_growth",
    )

    COMPLIANCE_MONTHLY_FIELDS = (
        "ending_total_cases",
        "cases_created_during_month",
        "ending_open_cases",
        "ending_resolved_cases",
        "ending_closed_cases",
        "ending_total_alerts",
        "alerts_created_during_month",
        "ending_low_risk_customers",
        "ending_medium_risk_customers",
        "ending_high_risk_customers",
        "ending_critical_risk_customers",
    )

    OPERATIONS_MONTHLY_FIELDS = (
        "ending_total_tasks",
        "tasks_created_during_month",
        "tasks_completed_during_month",
        "ending_open_tasks",
        "ending_overdue_tasks",
        "tasks_completed_within_sla_during_month",
        "tasks_completed_breached_sla_during_month",
        "ending_total_workflows",
        "workflows_started_during_month",
        "workflows_completed_during_month",
        "workflows_failed_during_month",
        "ending_active_workflows",
        "workflows_completed_within_sla_during_month",
        "workflows_completed_breached_sla_during_month",
    )

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _day_bounds(
        aggregation_date: date,
    ) -> tuple[datetime, datetime]:
        start = datetime.combine(
            aggregation_date,
            time.min,
            tzinfo=timezone.utc,
        )
        end = start + timedelta(days=1)

        return start, end

    @staticmethod
    def _month_bounds(
        month_start: date,
    ) -> tuple[date, date]:
        days = monthrange(
            month_start.year,
            month_start.month,
        )[1]

        return (
            month_start,
            month_start + timedelta(days=days),
        )

    @staticmethod
    def _row_metrics(
        row: Any,
        fields: tuple[str, ...],
    ) -> dict[str, int]:
        values = row._mapping

        return {field: int(values[field] or 0) for field in fields}

    @staticmethod
    def _count_filter(
        model: Any,
        *conditions: Any,
    ) -> Any:
        return func.count(model.id).filter(*conditions)

    def _count(
        self,
        model: Any,
        *conditions: Any,
    ) -> int:
        statement = select(
            func.count(model.id),
        ).where(*conditions)

        return int(self.db.scalar(statement) or 0)

    def collect_daily_event_metrics(
        self,
        *,
        aggregation_date: date,
    ) -> dict[str, int]:
        """Collect all events that occurred during one UTC calendar day."""

        day_start, day_end = self._day_bounds(
            aggregation_date,
        )

        customer_row = self.db.execute(
            select(
                self._count_filter(
                    Customer,
                    Customer.created_at >= day_start,
                    Customer.created_at < day_end,
                ).label(
                    "customers_registered_during_day",
                ),
            )
        ).one()

        verification_approvals = self._count(
            IdentityVerificationCase,
            IdentityVerificationCase.status == VerificationStatus.APPROVED,
            IdentityVerificationCase.completed_at >= day_start,
            IdentityVerificationCase.completed_at < day_end,
        )

        compliance_row = self.db.execute(
            select(
                self._count_filter(
                    ComplianceCase,
                    ComplianceCase.created_at >= day_start,
                    ComplianceCase.created_at < day_end,
                ).label(
                    "cases_created_during_day",
                ),
            )
        ).one()

        alert_row = self.db.execute(
            select(
                self._count_filter(
                    TransactionMonitoringResult,
                    TransactionMonitoringResult.result
                    == TransactionMonitoringOutcome.MATCHED,
                    TransactionMonitoringResult.created_at >= day_start,
                    TransactionMonitoringResult.created_at < day_end,
                ).label(
                    "alerts_created_during_day",
                ),
            )
            .select_from(TransactionMonitoringResult)
            .join(
                AMLRule,
                TransactionMonitoringResult.rule_id == AMLRule.id,
            )
        ).one()

        task_row = self.db.execute(
            select(
                self._count_filter(
                    Task,
                    Task.created_at >= day_start,
                    Task.created_at < day_end,
                ).label(
                    "tasks_created_during_day",
                ),
                self._count_filter(
                    Task,
                    Task.completed_at >= day_start,
                    Task.completed_at < day_end,
                    Task.status == TaskStatus.COMPLETED,
                ).label(
                    "tasks_completed_during_day",
                ),
                self._count_filter(
                    Task,
                    Task.completed_at >= day_start,
                    Task.completed_at < day_end,
                    Task.status == TaskStatus.COMPLETED,
                    Task.sla_status == SLAStatus.COMPLETED,
                ).label(
                    "tasks_completed_within_sla_during_day",
                ),
                self._count_filter(
                    Task,
                    Task.completed_at >= day_start,
                    Task.completed_at < day_end,
                    Task.status == TaskStatus.COMPLETED,
                    Task.sla_status == SLAStatus.BREACHED,
                ).label(
                    "tasks_completed_breached_sla_during_day",
                ),
            )
        ).one()

        workflow_row = self.db.execute(
            select(
                self._count_filter(
                    WorkflowExecution,
                    WorkflowExecution.started_at >= day_start,
                    WorkflowExecution.started_at < day_end,
                ).label(
                    "workflows_started_during_day",
                ),
                self._count_filter(
                    WorkflowExecution,
                    WorkflowExecution.completed_at >= day_start,
                    WorkflowExecution.completed_at < day_end,
                    WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
                ).label(
                    "workflows_completed_during_day",
                ),
                self._count_filter(
                    WorkflowExecution,
                    WorkflowExecution.completed_at >= day_start,
                    WorkflowExecution.completed_at < day_end,
                    WorkflowExecution.status == WorkflowExecutionStatus.FAILED,
                ).label(
                    "workflows_failed_during_day",
                ),
                self._count_filter(
                    WorkflowExecution,
                    WorkflowExecution.completed_at >= day_start,
                    WorkflowExecution.completed_at < day_end,
                    WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
                    WorkflowExecution.sla_status == SLAStatus.COMPLETED,
                ).label(
                    "workflows_completed_within_sla_during_day",
                ),
                self._count_filter(
                    WorkflowExecution,
                    WorkflowExecution.completed_at >= day_start,
                    WorkflowExecution.completed_at < day_end,
                    WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
                    WorkflowExecution.sla_status == SLAStatus.BREACHED,
                ).label(
                    "workflows_completed_breached_sla_during_day",
                ),
            )
        ).one()

        metrics = {}

        metrics.update(
            self._row_metrics(
                customer_row,
                ("customers_registered_during_day",),
            )
        )
        metrics["verification_approvals_during_day"] = verification_approvals

        metrics.update(
            self._row_metrics(
                compliance_row,
                ("cases_created_during_day",),
            )
        )
        metrics.update(
            self._row_metrics(
                alert_row,
                ("alerts_created_during_day",),
            )
        )

        metrics.update(
            self._row_metrics(
                task_row,
                (
                    "tasks_created_during_day",
                    "tasks_completed_during_day",
                    "tasks_completed_within_sla_during_day",
                    "tasks_completed_breached_sla_during_day",
                ),
            )
        )

        metrics.update(
            self._row_metrics(
                workflow_row,
                (
                    "workflows_started_during_day",
                    "workflows_completed_during_day",
                    "workflows_failed_during_day",
                    "workflows_completed_within_sla_during_day",
                    "workflows_completed_breached_sla_during_day",
                ),
            )
        )

        return metrics

    def update_daily_event_metrics(
        self,
        *,
        aggregation_date: date,
        metrics: dict[str, int],
    ) -> None:
        """Persist calculated daily event metrics onto existing snapshots."""

        snapshots = (
            self.db.get(
                CustomerAnalyticsDaily,
                aggregation_date,
            ),
            self.db.get(
                ComplianceAnalyticsDaily,
                aggregation_date,
            ),
            self.db.get(
                OperationsAnalyticsDaily,
                aggregation_date,
            ),
        )

        if any(snapshot is None for snapshot in snapshots):
            raise ValueError(
                "Daily analytics snapshot is missing for "
                f"{aggregation_date.isoformat()}.",
            )

        customer_snapshot, compliance_snapshot, operations_snapshot = snapshots

        for field in self.CUSTOMER_EVENT_FIELDS:
            setattr(
                customer_snapshot,
                field,
                int(metrics.get(field, 0) or 0),
            )

        for field in self.COMPLIANCE_EVENT_FIELDS:
            setattr(
                compliance_snapshot,
                field,
                int(metrics.get(field, 0) or 0),
            )

        for field in self.OPERATIONS_EVENT_FIELDS:
            setattr(
                operations_snapshot,
                field,
                int(metrics.get(field, 0) or 0),
            )

        self.db.flush()

    def _get_daily_rows(
        self,
        model: Any,
        month_start: date,
    ) -> list[Any]:
        _, month_end = self._month_bounds(
            month_start,
        )

        statement = (
            select(model)
            .where(
                model.snapshot_date >= month_start,
                model.snapshot_date < month_end,
            )
            .order_by(
                model.snapshot_date.asc(),
            )
        )

        return list(
            self.db.scalars(statement),
        )

    def get_customer_daily_rows(
        self,
        *,
        month_start: date,
    ) -> list[CustomerAnalyticsDaily]:
        return self._get_daily_rows(
            CustomerAnalyticsDaily,
            month_start,
        )

    def get_compliance_daily_rows(
        self,
        *,
        month_start: date,
    ) -> list[ComplianceAnalyticsDaily]:
        return self._get_daily_rows(
            ComplianceAnalyticsDaily,
            month_start,
        )

    def get_operations_daily_rows(
        self,
        *,
        month_start: date,
    ) -> list[OperationsAnalyticsDaily]:
        return self._get_daily_rows(
            OperationsAnalyticsDaily,
            month_start,
        )

    def get_previous_customer_snapshot(
        self,
        *,
        month_start: date,
    ) -> CustomerAnalyticsDaily | None:
        statement = (
            select(CustomerAnalyticsDaily)
            .where(
                CustomerAnalyticsDaily.snapshot_date < month_start,
            )
            .order_by(
                CustomerAnalyticsDaily.snapshot_date.desc(),
            )
            .limit(1)
        )

        return self.db.scalar(statement)

    def _save_monthly(
        self,
        *,
        model: Any,
        month_start: date,
        captured_at: datetime,
        metrics: dict[str, int],
        fields: tuple[str, ...],
    ) -> Any:
        row = self.db.get(
            model,
            month_start,
        )

        if row is None:
            row = model(
                month_start=month_start,
            )
            self.db.add(row)

        for field in fields:
            setattr(
                row,
                field,
                int(metrics[field] or 0),
            )

        row.captured_at = captured_at

        self.db.flush()

        return row

    def save_customer_monthly(
        self,
        *,
        month_start: date,
        ending_total_customers: int,
        customers_registered_during_month: int,
        verification_approvals_during_month: int,
        customer_growth: int,
        captured_at: datetime,
    ) -> Any:
        metrics = {
            "ending_total_customers": ending_total_customers,
            "customers_registered_during_month": (customers_registered_during_month),
            "verification_approvals_during_month": (
                verification_approvals_during_month
            ),
            "customer_growth": customer_growth,
        }

        return self._save_monthly(
            model=CustomerAnalyticsMonthly,
            month_start=month_start,
            captured_at=captured_at,
            metrics=metrics,
            fields=self.CUSTOMER_MONTHLY_FIELDS,
        )

    def save_compliance_monthly(
        self,
        *,
        month_start: date,
        metrics: dict[str, int],
        captured_at: datetime,
    ) -> Any:
        return self._save_monthly(
            model=ComplianceAnalyticsMonthly,
            month_start=month_start,
            captured_at=captured_at,
            metrics=metrics,
            fields=self.COMPLIANCE_MONTHLY_FIELDS,
        )

    def save_operations_monthly(
        self,
        *,
        month_start: date,
        metrics: dict[str, int],
        captured_at: datetime,
    ) -> Any:
        return self._save_monthly(
            model=OperationsAnalyticsMonthly,
            month_start=month_start,
            captured_at=captured_at,
            metrics=metrics,
            fields=self.OPERATIONS_MONTHLY_FIELDS,
        )
