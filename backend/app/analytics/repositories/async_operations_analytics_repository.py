"""Async tenant-scoped operational analytics queries."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.models.operations_daily import OperationsAnalyticsDaily
from app.models.task import Task
from app.models.user import User
from app.models.workflow import Workflow, WorkflowExecution
from app.utils.enums import SLAStatus, TaskStatus, WorkflowExecutionStatus


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


class AsyncOperationsAnalyticsRepository:
    OPEN_TASK_STATUSES = (TaskStatus.NEW, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS)

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active = db.info.get("tenant_id")
        if active is not None and active != tenant_id:
            raise ValueError(
                "Analytics repository tenant does not match session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    @staticmethod
    def _start(value: date) -> datetime:
        return datetime.combine(value, time.min, tzinfo=timezone.utc)

    @staticmethod
    def _end(value: date) -> datetime:
        return datetime.combine(
            value + timedelta(days=1), time.min, tzinfo=timezone.utc
        )

    async def get_employees_by_ids(self, employee_ids: set[UUID]) -> dict[UUID, User]:
        if not employee_ids:
            return {}
        result = await self.db.scalars(
            select(User).where(
                User.tenant_id == self.tenant_id, User.id.in_(employee_ids)
            )
        )
        return {item.id: item for item in result.all()}

    async def get_daily_snapshots(
        self, *, start_date: date, end_date: date
    ) -> list[OperationsAnalyticsDaily]:
        result = await self.db.scalars(
            select(OperationsAnalyticsDaily)
            .where(
                OperationsAnalyticsDaily.tenant_id == self.tenant_id,
                OperationsAnalyticsDaily.snapshot_date >= start_date,
                OperationsAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(OperationsAnalyticsDaily.snapshot_date.asc())
        )
        return list(result.all())

    async def get_latest_snapshot(
        self, *, end_date: date
    ) -> OperationsAnalyticsDaily | None:
        return await self.db.scalar(
            select(OperationsAnalyticsDaily)
            .where(
                OperationsAnalyticsDaily.tenant_id == self.tenant_id,
                OperationsAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(OperationsAnalyticsDaily.snapshot_date.desc())
            .limit(1)
        )

    async def get_workflow_completion_metrics(
        self, *, start_date: date, end_date: date
    ) -> tuple[int, float | None]:
        stmt = (
            select(
                func.count(WorkflowExecution.id).label("completed_count"),
                func.avg(
                    func.extract(
                        "epoch",
                        WorkflowExecution.completed_at - WorkflowExecution.started_at,
                    )
                ).label("average_completion_seconds"),
            )
            .select_from(WorkflowExecution)
            .join(Workflow, Workflow.id == WorkflowExecution.workflow_id)
            .where(
                Workflow.tenant_id == self.tenant_id,
                WorkflowExecution.tenant_id == self.tenant_id,
                WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
                WorkflowExecution.completed_at >= self._start(start_date),
                WorkflowExecution.completed_at < self._end(end_date),
                WorkflowExecution.completed_at.is_not(None),
            )
        )
        row = (await self.db.execute(stmt)).one()
        avg = row.average_completion_seconds
        return int(row.completed_count or 0), (
            round(float(avg) / 3600, 2) if avg is not None else None
        )

    async def get_task_resolution_metrics(
        self, *, start_date: date, end_date: date
    ) -> tuple[int, float | None]:
        stmt = select(
            func.count(Task.id).label("completed_count"),
            func.avg(func.extract("epoch", Task.completed_at - Task.created_at)).label(
                "average_resolution_seconds"
            ),
        ).where(
            Task.tenant_id == self.tenant_id,
            Task.status == TaskStatus.COMPLETED,
            Task.completed_at >= self._start(start_date),
            Task.completed_at < self._end(end_date),
            Task.completed_at.is_not(None),
        )
        row = (await self.db.execute(stmt)).one()
        avg = row.average_resolution_seconds
        return int(row.completed_count or 0), (
            round(float(avg) / 3600, 2) if avg is not None else None
        )

    async def get_employee_completed_metrics(
        self, *, start_date: date, end_date: date
    ) -> list[EmployeeCompletedTaskMetrics]:
        stmt = (
            select(
                User.id.label("employee_id"),
                func.concat(User.first_name, " ", User.last_name).label(
                    "employee_name"
                ),
                User.department.label("department"),
                User.role.label("user_role"),
                func.count(Task.id).label("tasks_completed"),
                func.avg(
                    func.extract("epoch", Task.completed_at - Task.created_at)
                ).label("average_resolution_seconds"),
            )
            .select_from(Task)
            .join(User, Task.assigned_to == User.id)
            .where(
                Task.tenant_id == self.tenant_id,
                User.tenant_id == self.tenant_id,
                Task.status == TaskStatus.COMPLETED,
                Task.completed_at >= self._start(start_date),
                Task.completed_at < self._end(end_date),
                Task.completed_at.is_not(None),
            )
            .group_by(
                User.id, User.first_name, User.last_name, User.department, User.role
            )
            .order_by(
                func.count(Task.id).desc(), User.first_name.asc(), User.last_name.asc()
            )
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            EmployeeCompletedTaskMetrics(
                employee_id=row.employee_id,
                employee_name=str(row.employee_name),
                department=str(row.department) if row.department is not None else None,
                user_role=str(row.user_role),
                tasks_completed=int(row.tasks_completed or 0),
                average_resolution_time_hours=(
                    round(float(row.average_resolution_seconds) / 3600, 2)
                    if row.average_resolution_seconds is not None
                    else None
                ),
            )
            for row in rows
        ]

    async def get_employee_open_metrics(
        self, *, end_date: date
    ) -> list[EmployeeOpenTaskMetrics]:
        end = self._end(end_date)
        stmt = (
            select(
                User.id.label("employee_id"),
                func.count(Task.id).label("open_tasks"),
                func.count(Task.id)
                .filter(Task.due_date.is_not(None), Task.due_date < end)
                .label("overdue_tasks"),
            )
            .select_from(Task)
            .join(User, Task.assigned_to == User.id)
            .where(
                Task.tenant_id == self.tenant_id,
                User.tenant_id == self.tenant_id,
                Task.created_at < end,
                Task.status.in_(self.OPEN_TASK_STATUSES),
            )
            .group_by(User.id)
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            EmployeeOpenTaskMetrics(
                row.employee_id, int(row.open_tasks or 0), int(row.overdue_tasks or 0)
            )
            for row in rows
        ]

    async def get_sla_delay_metrics(
        self, *, start_date: date, end_date: date
    ) -> float | None:
        stmt = select(
            func.avg(func.extract("epoch", Task.completed_at - Task.due_date))
        ).where(
            Task.tenant_id == self.tenant_id,
            Task.status == TaskStatus.COMPLETED,
            Task.sla_status == SLAStatus.BREACHED,
            Task.completed_at >= self._start(start_date),
            Task.completed_at < self._end(end_date),
            Task.completed_at.is_not(None),
            Task.due_date.is_not(None),
        )
        avg = await self.db.scalar(stmt)
        return None if avg is None else round(float(avg) / 3600, 2)
