from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.task_assignment_rule import TaskAssignmentRule
from app.models.user import User
from app.models.workflow import WorkflowExecution, WorkflowStep, WorkflowStepExecution
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import TaskPriority, TaskStatus


class TaskRepository(TenantScopedRepository[Task]):
    """Tenant-scoped tasks with tenant-checked assignee/workflow relationships."""

    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved_tenant_id = tenant_id or db.info.get("tenant_id")
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for tasks.")
        session_tenant_id = db.info.get("tenant_id")
        if session_tenant_id is not None and session_tenant_id != resolved_tenant_id:
            raise ValueError(
                "The SQLAlchemy session is already bound to another tenant."
            )
        # Also scope relationship/lazy loads covered by tenant_filter.py.
        db.info["tenant_id"] = resolved_tenant_id
        super().__init__(db=db, model=Task, tenant_id=resolved_tenant_id)

    def _validate_relations(self, task: Task) -> None:
        if task.assigned_to is not None:
            user_id = self.db.scalar(
                select(User.id).where(
                    User.id == task.assigned_to,
                    User.tenant_id == self.tenant_id,
                )
            )
            if user_id is None:
                raise ValueError("Task assignee does not belong to the current tenant.")

        if task.workflow_execution_id is not None:
            execution_id = self.db.scalar(
                select(WorkflowExecution.id).where(
                    WorkflowExecution.id == task.workflow_execution_id,
                    WorkflowExecution.tenant_id == self.tenant_id,
                )
            )
            if execution_id is None:
                raise ValueError("Task workflow execution belongs to another tenant.")

        if task.workflow_step_execution_id is not None:
            step_execution_id = self.db.scalar(
                select(WorkflowStepExecution.id)
                .join(
                    WorkflowExecution,
                    WorkflowStepExecution.workflow_execution_id == WorkflowExecution.id,
                )
                .join(
                    WorkflowStep,
                    WorkflowStepExecution.workflow_step_id == WorkflowStep.id,
                )
                .where(
                    WorkflowStepExecution.id == task.workflow_step_execution_id,
                    WorkflowExecution.tenant_id == self.tenant_id,
                    WorkflowStep.tenant_id == self.tenant_id,
                )
            )
            if step_execution_id is None:
                raise ValueError(
                    "Task workflow-step execution belongs to another tenant."
                )
            if task.workflow_execution_id is not None:
                step_parent_id = self.db.scalar(
                    select(WorkflowStepExecution.workflow_execution_id).where(
                        WorkflowStepExecution.id == task.workflow_step_execution_id,
                    )
                )
                if step_parent_id != task.workflow_execution_id:
                    raise ValueError(
                        "Task workflow execution and step execution do not match."
                    )

        if task.assignment_rule_id is not None:
            rule_id = self.db.scalar(
                select(TaskAssignmentRule.id).where(
                    TaskAssignmentRule.id == task.assignment_rule_id,
                    TaskAssignmentRule.tenant_id == self.tenant_id,
                )
            )
            if rule_id is None:
                raise ValueError("Task assignment rule belongs to another tenant.")

    def _assert_owned(self, task: Task) -> None:
        if task.tenant_id != self.tenant_id:
            raise ValueError("Task belongs to another tenant.")
        exists = self.db.scalar(
            select(Task.id).where(
                Task.id == task.id,
                Task.tenant_id == self.tenant_id,
            )
        )
        if exists is None:
            raise ValueError("Task does not belong to the current tenant.")

    def create(self, task: Task) -> Task:
        if task.tenant_id is not None and task.tenant_id != self.tenant_id:
            raise ValueError("Cannot create a task for another tenant.")
        self._validate_relations(task)
        return super().create(task)

    def get_by_id_for_update(self, task_id: UUID) -> Task | None:
        return self.query().filter(Task.id == task_id).with_for_update().first()

    def list_tasks(
        self,
        *,
        assigned_to: UUID | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Task], int]:
        if page < 1 or page_size < 1:
            raise ValueError("page and page_size must be positive integers.")
        query = self.query()
        if assigned_to is not None:
            query = query.filter(Task.assigned_to == assigned_to)
        if status is not None:
            query = query.filter(Task.status == status)
        if priority is not None:
            query = query.filter(Task.priority == priority)

        total = query.count()
        offset = (page - 1) * page_size
        tasks = (
            query.order_by(
                Task.due_date.asc().nullslast(),
                Task.created_at.desc(),
            )
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return tasks, total

    def update(self, task: Task) -> Task:
        self._assert_owned(task)
        self._validate_relations(task)
        self.db.flush()
        self.db.refresh(task)
        return task

    def delete(self, task: Task) -> None:
        self._assert_owned(task)
        self.db.delete(task)
        self.db.flush()
