from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.task import Task
from app.models.workflow import Workflow, WorkflowExecution
from app.services.notification_service import NotificationService
from app.services.tenant_context import resolve_tenant_context
from app.utils.date_time import utc_now
from app.utils.enums import (
    NotificationChannel,
    NotificationEventType,
    SLAStatus,
    TaskStatus,
    WorkflowExecutionStatus,
)


class SLAService:
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = resolve_tenant_context(
            db, tenant_id, resource_name="SLA evaluation"
        )
        self.notification_service = NotificationService(db, tenant_id=self.tenant_id)

    @staticmethod
    def calculate_status(
        *,
        created_at: datetime,
        due_date: datetime | None,
        completed_at: datetime | None = None,
        now: datetime | None = None,
    ) -> SLAStatus | None:
        if due_date is None:
            return None
        current_time = now or utc_now()
        if completed_at is not None:
            return (
                SLAStatus.COMPLETED if completed_at <= due_date else SLAStatus.BREACHED
            )
        if due_date <= current_time:
            return SLAStatus.BREACHED
        total_duration = due_date - created_at
        if total_duration <= timedelta(0):
            return SLAStatus.BREACHED
        remaining_duration = due_date - current_time
        approaching_threshold = total_duration * (
            settings.SLA_APPROACHING_THRESHOLD_PERCENT / 100.0
        )
        if remaining_duration <= approaching_threshold:
            return SLAStatus.APPROACHING_DEADLINE
        return SLAStatus.WITHIN_SLA

    def evaluate_task(self, task: Task, *, now: datetime | None = None) -> bool:
        if task.tenant_id != self.tenant_id:
            raise ValueError("Cannot evaluate a task from another tenant.")
        current_time = now or utc_now()
        new_status = self.calculate_status(
            created_at=task.created_at,
            due_date=task.due_date,
            completed_at=task.completed_at,
            now=current_time,
        )
        if task.sla_status == new_status:
            return False
        previous_status = task.sla_status
        task.sla_status = new_status
        if (
            new_status == SLAStatus.APPROACHING_DEADLINE
            and previous_status != SLAStatus.APPROACHING_DEADLINE
        ):
            self._notify_task(
                task,
                event_type=NotificationEventType.TASK_SLA_APPROACHING,
                title="Task approaching SLA deadline",
                message=f'The task "{task.title}" is approaching its SLA deadline.',
            )
        elif new_status == SLAStatus.BREACHED and previous_status != SLAStatus.BREACHED:
            self._notify_task(
                task,
                event_type=NotificationEventType.TASK_SLA_BREACHED,
                title="Task SLA breached",
                message=f'The task "{task.title}" has breached its SLA deadline.',
            )
        return True

    def evaluate_workflow(
        self, execution: WorkflowExecution, *, now: datetime | None = None
    ) -> bool:
        if execution.tenant_id != self.tenant_id:
            raise ValueError(
                "Cannot evaluate a workflow execution from another tenant."
            )
        current_time = now or utc_now()
        new_status = self.calculate_status(
            created_at=execution.started_at,
            due_date=execution.due_date,
            completed_at=(
                execution.completed_at
                if execution.status == WorkflowExecutionStatus.COMPLETED
                else None
            ),
            now=current_time,
        )
        if execution.sla_status == new_status:
            return False
        previous_status = execution.sla_status
        execution.sla_status = new_status
        if (
            new_status == SLAStatus.APPROACHING_DEADLINE
            and previous_status != SLAStatus.APPROACHING_DEADLINE
        ):
            self._notify_workflow(
                execution,
                event_type=NotificationEventType.WORKFLOW_SLA_APPROACHING,
                title="Workflow approaching SLA deadline",
                message=(
                    f"Workflow execution {execution.id} "
                    "is approaching its SLA deadline."
                ),
            )
        elif new_status == SLAStatus.BREACHED and previous_status != SLAStatus.BREACHED:
            self._notify_workflow(
                execution,
                event_type=NotificationEventType.WORKFLOW_SLA_BREACHED,
                title="Workflow SLA breached",
                message=(
                    f"Workflow execution {execution.id} has breached its SLA deadline."
                ),
            )
        return True

    def check_all(self, *, now: datetime | None = None) -> int:
        current_time = now or utc_now()
        changed_count = 0
        tasks = (
            self.db.query(Task)
            .filter(
                Task.tenant_id == self.tenant_id,
                Task.due_date.isnot(None),
                Task.status.notin_([TaskStatus.COMPLETED, TaskStatus.CANCELLED]),
            )
            .with_for_update()
            .all()
        )
        for task in tasks:
            if self.evaluate_task(task, now=current_time):
                changed_count += 1

        executions = (
            self.db.query(WorkflowExecution)
            .join(Workflow, Workflow.id == WorkflowExecution.workflow_id)
            .filter(
                Workflow.tenant_id == self.tenant_id,
                WorkflowExecution.tenant_id == self.tenant_id,
                WorkflowExecution.due_date.isnot(None),
                WorkflowExecution.status == WorkflowExecutionStatus.IN_PROGRESS,
            )
            .with_for_update()
            .all()
        )
        for execution in executions:
            if self.evaluate_workflow(execution, now=current_time):
                changed_count += 1
        self.db.commit()
        return changed_count

    def _notify_task(
        self,
        task: Task,
        *,
        event_type: NotificationEventType,
        title: str,
        message: str,
    ) -> None:
        if task.assigned_to is None:
            return
        self.notification_service.create_notification(
            user_id=task.assigned_to,
            title=title,
            message=message,
            event_type=event_type,
            resource_type="task",
            resource_id=task.id,
            channels=(NotificationChannel.IN_APP,),
        )

    def _notify_workflow(
        self,
        execution: WorkflowExecution,
        *,
        event_type: NotificationEventType,
        title: str,
        message: str,
    ) -> None:
        if execution.started_by is None:
            return
        self.notification_service.create_notification(
            user_id=execution.started_by,
            title=title,
            message=message,
            event_type=event_type,
            resource_type="workflow_execution",
            resource_id=execution.id,
            channels=(NotificationChannel.IN_APP,),
        )
