from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.models.operations_daily import OperationsAnalyticsDaily
from app.models.task import Task
from app.models.user import User
from app.models.workflow import WorkflowExecution
from app.utils.enums import (
    SLAStatus,
    TaskStatus,
    WorkflowExecutionStatus,
)


@dataclass(frozen=True)
class EmployeeCompletedTaskMetrics:
    employee_id: UUID
    employee_name: str
    department: str | None
    user_role: str
    tasks_completed: int
    average_resolution_time_hours: float | None


@dataclass(frozen=True)
class EmployeeOpenTaskMetrics:
    employee_id: UUID
    open_tasks: int
    overdue_tasks: int


class OperationsAnalyticsRepository:
    """Database operations for operational analytics."""

    OPEN_TASK_STATUSES = (
        TaskStatus.NEW,
        TaskStatus.ASSIGNED,
        TaskStatus.IN_PROGRESS,
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

    def get_employees_by_ids(
        self,
        employee_ids: set,
    ) -> dict:
        if not employee_ids:
            return {}

        statement = select(User).where(
            User.id.in_(employee_ids),
        )

        employees = self.db.scalars(statement).all()

        return {employee.id: employee for employee in employees}

    def get_daily_snapshots(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[OperationsAnalyticsDaily]:
        statement = (
            select(OperationsAnalyticsDaily)
            .where(
                OperationsAnalyticsDaily.snapshot_date >= start_date,
                OperationsAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(
                OperationsAnalyticsDaily.snapshot_date.asc(),
            )
        )

        return list(
            self.db.scalars(statement).all(),
        )

    def get_latest_snapshot(
        self,
        *,
        end_date: date,
    ) -> OperationsAnalyticsDaily | None:
        statement = (
            select(OperationsAnalyticsDaily)
            .where(
                OperationsAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(
                OperationsAnalyticsDaily.snapshot_date.desc(),
            )
            .limit(1)
        )

        return self.db.scalars(statement).first()

    def get_workflow_completion_metrics(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> tuple[int, float | None]:
        start_datetime = self._start_datetime(start_date)
        end_datetime = self._end_datetime_exclusive(end_date)

        statement = select(
            func.count(WorkflowExecution.id).label(
                "completed_count",
            ),
            func.avg(
                func.extract(
                    "epoch",
                    WorkflowExecution.completed_at - WorkflowExecution.started_at,
                )
            ).label(
                "average_completion_seconds",
            ),
        ).where(
            WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
            WorkflowExecution.completed_at >= start_datetime,
            WorkflowExecution.completed_at < end_datetime,
            WorkflowExecution.completed_at.is_not(None),
        )

        row = self.db.execute(statement).one()

        average_seconds = row._mapping["average_completion_seconds"]

        return (
            int(row._mapping["completed_count"] or 0),
            (
                round(
                    float(average_seconds) / 3600,
                    2,
                )
                if average_seconds is not None
                else None
            ),
        )

    def get_task_resolution_metrics(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> tuple[int, float | None]:
        start_datetime = self._start_datetime(start_date)
        end_datetime = self._end_datetime_exclusive(end_date)

        statement = select(
            func.count(Task.id).label(
                "completed_count",
            ),
            func.avg(
                func.extract(
                    "epoch",
                    Task.completed_at - Task.created_at,
                )
            ).label(
                "average_resolution_seconds",
            ),
        ).where(
            Task.status == TaskStatus.COMPLETED,
            Task.completed_at >= start_datetime,
            Task.completed_at < end_datetime,
            Task.completed_at.is_not(None),
        )

        row = self.db.execute(statement).one()

        average_seconds = row._mapping["average_resolution_seconds"]

        return (
            int(row._mapping["completed_count"] or 0),
            (
                round(
                    float(average_seconds) / 3600,
                    2,
                )
                if average_seconds is not None
                else None
            ),
        )

    def get_employee_completed_metrics(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[EmployeeCompletedTaskMetrics]:
        start_datetime = self._start_datetime(start_date)
        end_datetime = self._end_datetime_exclusive(end_date)

        statement = (
            select(
                User.id.label("employee_id"),
                func.concat(
                    User.first_name,
                    " ",
                    User.last_name,
                ).label("employee_name"),
                User.department.label("department"),
                User.role.label("user_role"),
                func.count(Task.id).label("tasks_completed"),
                func.avg(
                    func.extract(
                        "epoch",
                        Task.completed_at - Task.created_at,
                    )
                ).label(
                    "average_resolution_seconds",
                ),
            )
            .select_from(Task)
            .join(
                User,
                Task.assigned_to == User.id,
            )
            .where(
                Task.status == TaskStatus.COMPLETED,
                Task.completed_at >= start_datetime,
                Task.completed_at < end_datetime,
                Task.completed_at.is_not(None),
            )
            .group_by(
                User.id,
                User.first_name,
                User.last_name,
                User.department,
                User.role,
            )
            .order_by(
                func.count(Task.id).desc(),
                User.first_name.asc(),
                User.last_name.asc(),
            )
        )

        result = self.db.execute(statement)

        return [
            EmployeeCompletedTaskMetrics(
                employee_id=row._mapping["employee_id"],
                employee_name=str(
                    row._mapping["employee_name"],
                ),
                department=(
                    str(row._mapping["department"])
                    if row._mapping["department"] is not None
                    else None
                ),
                user_role=str(
                    row._mapping["user_role"],
                ),
                tasks_completed=int(
                    row._mapping["tasks_completed"] or 0,
                ),
                average_resolution_time_hours=(
                    round(
                        float(row._mapping["average_resolution_seconds"]) / 3600,
                        2,
                    )
                    if row._mapping["average_resolution_seconds"] is not None
                    else None
                ),
            )
            for row in result
        ]

    def get_employee_open_metrics(
        self,
        *,
        end_date: date,
    ) -> list[EmployeeOpenTaskMetrics]:
        end_datetime = self._end_datetime_exclusive(
            end_date,
        )

        statement = (
            select(
                User.id.label("employee_id"),
                func.count(Task.id).label(
                    "open_tasks",
                ),
                func.count(Task.id)
                .filter(
                    Task.due_date.is_not(None),
                    Task.due_date < end_datetime,
                )
                .label(
                    "overdue_tasks",
                ),
            )
            .select_from(Task)
            .join(
                User,
                Task.assigned_to == User.id,
            )
            .where(
                Task.created_at < end_datetime,
                Task.status.in_(
                    self.OPEN_TASK_STATUSES,
                ),
            )
            .group_by(
                User.id,
            )
        )

        result = self.db.execute(statement)

        return [
            EmployeeOpenTaskMetrics(
                employee_id=row._mapping["employee_id"],
                open_tasks=int(
                    row._mapping["open_tasks"] or 0,
                ),
                overdue_tasks=int(
                    row._mapping["overdue_tasks"] or 0,
                ),
            )
            for row in result
        ]

    def get_sla_delay_metrics(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> float | None:
        start_datetime = self._start_datetime(start_date)
        end_datetime = self._end_datetime_exclusive(end_date)

        statement = select(
            func.avg(
                func.extract(
                    "epoch",
                    Task.completed_at - Task.due_date,
                )
            ).label(
                "average_delay_seconds",
            )
        ).where(
            Task.status == TaskStatus.COMPLETED,
            Task.sla_status == SLAStatus.BREACHED,
            Task.completed_at >= start_datetime,
            Task.completed_at < end_datetime,
            Task.completed_at.is_not(None),
            Task.due_date.is_not(None),
        )

        average_seconds = self.db.scalar(statement)

        if average_seconds is None:
            return None

        return round(
            float(average_seconds) / 3600,
            2,
        )
