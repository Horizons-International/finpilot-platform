"""Async tenant-scoped executive dashboard aggregate queries."""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.models.compliance_daily import ComplianceAnalyticsDaily
from app.analytics.models.customer_daily import CustomerAnalyticsDaily
from app.analytics.models.operations_daily import OperationsAnalyticsDaily
from app.models.task import Task
from app.models.user import User
from app.models.workflow import Workflow, WorkflowExecution
from app.utils.enums import SLAStatus, TaskStatus, WorkflowExecutionStatus


class AsyncExecutiveDashboardRepository:
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
    def _end(value: date) -> datetime:
        return datetime.combine(
            value + timedelta(days=1), time.min, tzinfo=timezone.utc
        )

    async def get_customer_trend(
        self, *, start_date: date, end_date: date
    ) -> list[CustomerAnalyticsDaily]:
        rows = await self.db.scalars(
            select(CustomerAnalyticsDaily)
            .where(
                CustomerAnalyticsDaily.tenant_id == self.tenant_id,
                CustomerAnalyticsDaily.snapshot_date >= start_date,
                CustomerAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(CustomerAnalyticsDaily.snapshot_date)
        )
        return list(rows.all())

    async def get_latest_customer_snapshot(
        self, *, end_date: date
    ) -> CustomerAnalyticsDaily | None:
        return await self.db.scalar(
            select(CustomerAnalyticsDaily)
            .where(
                CustomerAnalyticsDaily.tenant_id == self.tenant_id,
                CustomerAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(CustomerAnalyticsDaily.snapshot_date.desc())
            .limit(1)
        )

    async def get_latest_compliance_snapshot(
        self, *, end_date: date
    ) -> ComplianceAnalyticsDaily | None:
        return await self.db.scalar(
            select(ComplianceAnalyticsDaily)
            .where(
                ComplianceAnalyticsDaily.tenant_id == self.tenant_id,
                ComplianceAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(ComplianceAnalyticsDaily.snapshot_date.desc())
            .limit(1)
        )

    async def get_latest_operations_snapshot(
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

    async def get_task_sla_metrics(
        self, *, start_date: date, end_date: date
    ) -> dict[str, int]:
        start_at = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        end_at = self._end(end_date)
        stmt = select(
            func.count(Task.id)
            .filter(
                Task.status == TaskStatus.COMPLETED,
                Task.completed_at >= start_at,
                Task.completed_at < end_at,
            )
            .label("tasks_completed"),
            func.count(Task.id)
            .filter(
                Task.status == TaskStatus.COMPLETED,
                Task.sla_status == SLAStatus.COMPLETED,
                Task.completed_at >= start_at,
                Task.completed_at < end_at,
            )
            .label("tasks_completed_within_sla"),
            func.count(Task.id)
            .filter(
                Task.status == TaskStatus.COMPLETED,
                Task.sla_status == SLAStatus.BREACHED,
                Task.completed_at >= start_at,
                Task.completed_at < end_at,
            )
            .label("tasks_completed_breached_sla"),
        ).where(Task.tenant_id == self.tenant_id)
        row = (await self.db.execute(stmt)).one()
        return {
            "tasks_completed": int(row.tasks_completed or 0),
            "tasks_completed_within_sla": int(row.tasks_completed_within_sla or 0),
            "tasks_completed_breached_sla": int(row.tasks_completed_breached_sla or 0),
        }

    async def get_workflow_sla_metrics(
        self, *, start_date: date, end_date: date
    ) -> dict[str, int]:
        start_at = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        end_at = self._end(end_date)
        stmt = (
            select(
                func.count(WorkflowExecution.id)
                .filter(
                    WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
                    WorkflowExecution.completed_at >= start_at,
                    WorkflowExecution.completed_at < end_at,
                )
                .label("workflows_completed"),
                func.count(WorkflowExecution.id)
                .filter(
                    WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
                    WorkflowExecution.sla_status == SLAStatus.COMPLETED,
                    WorkflowExecution.completed_at >= start_at,
                    WorkflowExecution.completed_at < end_at,
                )
                .label("workflows_completed_within_sla"),
                func.count(WorkflowExecution.id)
                .filter(
                    WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
                    WorkflowExecution.sla_status == SLAStatus.BREACHED,
                    WorkflowExecution.completed_at >= start_at,
                    WorkflowExecution.completed_at < end_at,
                )
                .label("workflows_completed_breached_sla"),
            )
            .select_from(WorkflowExecution)
            .join(Workflow, Workflow.id == WorkflowExecution.workflow_id)
            .where(
                Workflow.tenant_id == self.tenant_id,
                WorkflowExecution.tenant_id == self.tenant_id,
            )
        )
        row = (await self.db.execute(stmt)).one()
        return {
            "workflows_completed": int(row.workflows_completed or 0),
            "workflows_completed_within_sla": int(
                row.workflows_completed_within_sla or 0
            ),
            "workflows_completed_breached_sla": int(
                row.workflows_completed_breached_sla or 0
            ),
        }

    async def get_team_workload(
        self, *, end_date: date, department: str | None = None
    ) -> list[tuple[str, str | None, int, int]]:
        end_at = self._end(end_date)
        stmt = (
            select(
                func.coalesce(User.department, "Unassigned").label("team"),
                User.role.label("user_role"),
                func.count(Task.id).label("open_tasks"),
                func.count(Task.id)
                .filter(Task.due_date.is_not(None), Task.due_date < end_at)
                .label("overdue_tasks"),
            )
            .select_from(Task)
            .outerjoin(User, Task.assigned_to == User.id)
            .where(
                Task.tenant_id == self.tenant_id,
                Task.created_at < end_at,
                Task.status.in_(self.OPEN_TASK_STATUSES),
                or_(Task.assigned_to.is_(None), User.tenant_id == self.tenant_id),
            )
        )
        if department is not None:
            stmt = stmt.where(User.department == department)
        stmt = stmt.group_by(User.department, User.role).order_by(
            func.count(Task.id).desc()
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            (
                str(row.team),
                str(row.user_role) if row.user_role is not None else None,
                int(row.open_tasks or 0),
                int(row.overdue_tasks or 0),
            )
            for row in rows
        ]
