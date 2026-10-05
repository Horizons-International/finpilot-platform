from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.models.compliance_daily import ComplianceAnalyticsDaily
from app.analytics.models.customer_daily import CustomerAnalyticsDaily
from app.analytics.models.operations_daily import OperationsAnalyticsDaily
from app.models.task import Task
from app.models.user import User
from app.utils.enums import SLAStatus, TaskStatus


class ExecutiveDashboardRepository:
    """Read model for executive dashboard data."""

    OPEN_TASK_STATUSES = (
        TaskStatus.NEW,
        TaskStatus.ASSIGNED,
        TaskStatus.IN_PROGRESS,
    )

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _end_of_day_exclusive(end_date: date) -> datetime:
        return datetime.combine(
            end_date + timedelta(days=1),
            time.min,
            tzinfo=timezone.utc,
        )

    def get_customer_trend(
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
            .order_by(CustomerAnalyticsDaily.snapshot_date)
        )

        return list(self.db.scalars(statement).all())

    def get_latest_customer_snapshot(
        self,
        *,
        end_date: date,
    ) -> CustomerAnalyticsDaily | None:
        statement = (
            select(CustomerAnalyticsDaily)
            .where(
                CustomerAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(CustomerAnalyticsDaily.snapshot_date.desc())
            .limit(1)
        )

        return self.db.scalars(statement).first()

    def get_latest_compliance_snapshot(
        self,
        *,
        end_date: date,
    ) -> ComplianceAnalyticsDaily | None:
        statement = (
            select(ComplianceAnalyticsDaily)
            .where(
                ComplianceAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(ComplianceAnalyticsDaily.snapshot_date.desc())
            .limit(1)
        )

        return self.db.scalars(statement).first()

    def get_latest_operations_snapshot(
        self,
        *,
        end_date: date,
    ) -> OperationsAnalyticsDaily | None:
        statement = (
            select(OperationsAnalyticsDaily)
            .where(
                OperationsAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(OperationsAnalyticsDaily.snapshot_date.desc())
            .limit(1)
        )

        return self.db.scalars(statement).first()

    def get_task_sla_metrics(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> dict[str, int]:
        start_at = datetime.combine(
            start_date,
            time.min,
            tzinfo=timezone.utc,
        )
        end_at = self._end_of_day_exclusive(end_date)

        statement = select(
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
        )

        row = self.db.execute(statement).one()

        return {
            "tasks_completed": int(row.tasks_completed or 0),
            "tasks_completed_within_sla": int(row.tasks_completed_within_sla or 0),
            "tasks_completed_breached_sla": int(row.tasks_completed_breached_sla or 0),
        }

    def get_workflow_sla_metrics(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> dict[str, int]:
        from app.models.workflow import WorkflowExecution
        from app.utils.enums import WorkflowExecutionStatus

        start_at = datetime.combine(
            start_date,
            time.min,
            tzinfo=timezone.utc,
        )
        end_at = self._end_of_day_exclusive(end_date)

        statement = select(
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

        row = self.db.execute(statement).one()

        return {
            "workflows_completed": int(row.workflows_completed or 0),
            "workflows_completed_within_sla": int(
                row.workflows_completed_within_sla or 0
            ),
            "workflows_completed_breached_sla": int(
                row.workflows_completed_breached_sla or 0
            ),
        }

    def get_team_workload(
        self,
        *,
        end_date: date,
        department: str | None = None,
    ) -> list[tuple[str, str | None, int, int]]:
        end_at = self._end_of_day_exclusive(end_date)

        statement = (
            select(
                func.coalesce(
                    User.department,
                    "Unassigned",
                ).label("team"),
                User.role.label("user_role"),
                func.count(Task.id).label("open_tasks"),
                func.count(Task.id)
                .filter(
                    Task.due_date.is_not(None),
                    Task.due_date < end_at,
                )
                .label("overdue_tasks"),
            )
            .select_from(Task)
            .outerjoin(
                User,
                Task.assigned_to == User.id,
            )
            .where(
                Task.created_at < end_at,
                Task.status.in_(self.OPEN_TASK_STATUSES),
            )
        )

        if department is not None:
            statement = statement.where(
                User.department == department,
            )

        statement = statement.group_by(
            User.department,
            User.role,
        ).order_by(
            func.count(Task.id).desc(),
        )

        rows = self.db.execute(statement).all()

        return [
            (
                str(row.team),
                str(row.user_role) if row.user_role is not None else None,
                int(row.open_tasks or 0),
                int(row.overdue_tasks or 0),
            )
            for row in rows
        ]
