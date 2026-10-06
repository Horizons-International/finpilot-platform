from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.analytics.repositories.operations_analytics_repository import (
    OperationsAnalyticsRepository,
)
from app.schemas.operations_analytics import (
    EmployeeTaskPerformance,
    HistoricalComparison,
    OperationsAnalyticsFilters,
    OperationsAnalyticsResponse,
    SLAPerformance,
    TaskPerformance,
    WorkflowPerformance,
    WorkflowTrendPoint,
)
from app.utils.date_time import utc_now
from app.utils.errors import bad_request


class OperationsAnalyticsService:
    DEFAULT_LOOKBACK_DAYS = 30
    MAX_LOOKBACK_DAYS = 366

    def __init__(self, db: Session) -> None:
        self.repository = OperationsAnalyticsRepository(db)

    @staticmethod
    def _percentage_change(
        current: float,
        previous: float,
    ) -> float | None:
        if previous == 0:
            return None

        return round(
            ((current - previous) / previous) * 100,
            2,
        )

    @staticmethod
    def _sla_compliance_percentage(
        completed: int,
        completed_within_sla: int,
    ) -> float | None:
        if completed == 0:
            return None

        return round(
            (completed_within_sla / completed) * 100,
            2,
        )

    @staticmethod
    def _period_bounds(
        *,
        start_date: date,
        end_date: date,
    ) -> tuple[date, date]:
        period_days = (end_date - start_date).days + 1

        previous_end = start_date - timedelta(days=1)

        previous_start = previous_end - timedelta(days=period_days - 1)

        return previous_start, previous_end

    def _aggregate_daily_rows(
        self,
        rows,
    ) -> dict[str, int]:
        return {
            "workflows_started": sum(row.workflows_started_during_day for row in rows),
            "workflows_completed": sum(
                row.workflows_completed_during_day for row in rows
            ),
            "workflows_failed": sum(row.workflows_failed_during_day for row in rows),
            "tasks_completed": sum(row.tasks_completed_during_day for row in rows),
            "tasks_completed_within_sla": sum(
                row.tasks_completed_within_sla_during_day for row in rows
            ),
            "tasks_completed_breached_sla": sum(
                row.tasks_completed_breached_sla_during_day for row in rows
            ),
        }

    def get_operations_performance(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> OperationsAnalyticsResponse:
        normalized_end_date = end_date or utc_now().date()

        normalized_start_date = start_date or (
            normalized_end_date
            - timedelta(
                days=self.DEFAULT_LOOKBACK_DAYS - 1,
            )
        )

        if normalized_start_date > normalized_end_date:
            raise bad_request(
                "start_date cannot be after end_date.",
            )

        lookback_days = (normalized_end_date - normalized_start_date).days + 1

        if lookback_days > self.MAX_LOOKBACK_DAYS:
            raise bad_request(
                "Analytics date range cannot exceed 366 days.",
            )

        previous_start_date, previous_end_date = self._period_bounds(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        current_rows = self.repository.get_daily_snapshots(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        previous_rows = self.repository.get_daily_snapshots(
            start_date=previous_start_date,
            end_date=previous_end_date,
        )

        latest_snapshot = self.repository.get_latest_snapshot(
            end_date=normalized_end_date,
        )

        current_metrics = self._aggregate_daily_rows(
            current_rows,
        )

        previous_metrics = self._aggregate_daily_rows(
            previous_rows,
        )

        (
            _,
            average_workflow_completion_hours,
        ) = self.repository.get_workflow_completion_metrics(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        (
            _,
            average_task_resolution_hours,
        ) = self.repository.get_task_resolution_metrics(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        employee_completed = self.repository.get_employee_completed_metrics(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        employee_open = self.repository.get_employee_open_metrics(
            end_date=normalized_end_date,
        )

        employee_open_by_id = {row.employee_id: row for row in employee_open}

        employee_performance = []

        for row in employee_completed:
            open_metrics = employee_open_by_id.get(row.employee_id)

            employee_performance.append(
                EmployeeTaskPerformance(
                    employee_id=row.employee_id,
                    employee_name=row.employee_name,
                    department=row.department,
                    user_role=row.user_role,
                    tasks_completed_during_period=row.tasks_completed,
                    open_tasks_at_end=open_metrics.open_tasks if open_metrics else 0,
                    overdue_tasks_at_end=(
                        open_metrics.overdue_tasks if open_metrics else 0
                    ),
                    average_resolution_time_hours=row.average_resolution_time_hours,
                )
            )

        completed_employee_ids = {row.employee_id for row in employee_completed}

        open_only_employee_ids = {
            row.employee_id
            for row in employee_open
            if row.employee_id not in completed_employee_ids
        }

        employees = self.repository.get_employees_by_ids(
            open_only_employee_ids,
        )

        for open_row in employee_open:
            if open_row.employee_id in completed_employee_ids:
                continue

            employee = employees.get(
                open_row.employee_id,
            )

            if employee is None:
                continue

            employee_performance.append(
                EmployeeTaskPerformance(
                    employee_id=employee.id,
                    employee_name=f"{employee.first_name} {employee.last_name}",
                    department=employee.department,
                    user_role=str(employee.role),
                    tasks_completed_during_period=0,
                    open_tasks_at_end=open_row.open_tasks,
                    overdue_tasks_at_end=open_row.overdue_tasks,
                    average_resolution_time_hours=None,
                )
            )

        employee_performance.sort(
            key=lambda row: (
                -row.tasks_completed_during_period,
                -row.open_tasks_at_end,
                row.employee_name,
            )
        )

        average_delay_hours = self.repository.get_sla_delay_metrics(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        current_sla_compliance = self._sla_compliance_percentage(
            current_metrics["tasks_completed"],
            current_metrics["tasks_completed_within_sla"],
        )

        previous_sla_compliance = self._sla_compliance_percentage(
            previous_metrics["tasks_completed"],
            previous_metrics["tasks_completed_within_sla"],
        )

        return OperationsAnalyticsResponse(
            generated_at=utc_now(),
            filters=OperationsAnalyticsFilters(
                start_date=normalized_start_date,
                end_date=normalized_end_date,
            ),
            workflow=WorkflowPerformance(
                workflows_started_during_period=(current_metrics["workflows_started"]),
                workflows_completed_during_period=(
                    current_metrics["workflows_completed"]
                ),
                workflows_failed_during_period=(current_metrics["workflows_failed"]),
                average_completion_time_hours=(average_workflow_completion_hours),
                ending_active_workflows=(
                    latest_snapshot.ending_active_workflows if latest_snapshot else 0
                ),
                trend=[
                    WorkflowTrendPoint(
                        snapshot_date=row.snapshot_date,
                        workflows_started_during_day=(row.workflows_started_during_day),
                        workflows_completed_during_day=(
                            row.workflows_completed_during_day
                        ),
                        workflows_failed_during_day=(row.workflows_failed_during_day),
                    )
                    for row in current_rows
                ],
            ),
            tasks=TaskPerformance(
                tasks_completed_during_period=(current_metrics["tasks_completed"]),
                ending_open_tasks=(
                    latest_snapshot.ending_open_tasks if latest_snapshot else 0
                ),
                ending_overdue_tasks=(
                    latest_snapshot.ending_overdue_tasks if latest_snapshot else 0
                ),
                average_resolution_time_hours=(average_task_resolution_hours),
                employees=employee_performance,
            ),
            sla=SLAPerformance(
                tasks_completed_during_period=(current_metrics["tasks_completed"]),
                tasks_completed_within_sla_during_period=(
                    current_metrics["tasks_completed_within_sla"]
                ),
                tasks_completed_breached_sla_during_period=(
                    current_metrics["tasks_completed_breached_sla"]
                ),
                sla_compliance_percentage=(current_sla_compliance),
                sla_breaches_during_period=(
                    current_metrics["tasks_completed_breached_sla"]
                ),
                ending_sla_breaches=(
                    latest_snapshot.ending_tasks_sla_breached if latest_snapshot else 0
                ),
                average_delay_hours=average_delay_hours,
            ),
            historical_comparison=HistoricalComparison(
                previous_start_date=previous_start_date,
                previous_end_date=previous_end_date,
                workflows_completed_change_percentage=(
                    self._percentage_change(
                        current_metrics["workflows_completed"],
                        previous_metrics["workflows_completed"],
                    )
                ),
                tasks_completed_change_percentage=(
                    self._percentage_change(
                        current_metrics["tasks_completed"],
                        previous_metrics["tasks_completed"],
                    )
                ),
                sla_compliance_change_percentage_points=(
                    round(
                        current_sla_compliance - previous_sla_compliance,
                        2,
                    )
                    if (
                        current_sla_compliance is not None
                        and previous_sla_compliance is not None
                    )
                    else None
                ),
            ),
        )
