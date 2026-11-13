"""Tenant-safe async repository for tasks, comments and status history."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.task import Task, TaskComment, TaskStatusHistory
from app.models.task_assignment_rule import TaskAssignmentRule
from app.models.user import User
from app.models.workflow import WorkflowExecution, WorkflowStep, WorkflowStepExecution
from app.repositories.async_tenant_scoped_repository import AsyncTenantScopedRepository
from app.utils.enums import TaskPriority, TaskStatus


class AsyncTaskRepository(AsyncTenantScopedRepository[Task]):
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(db, Task, tenant_id)

    async def _validate_relations(self, task: Task) -> None:
        if task.assigned_to is not None:
            exists = await self.db.scalar(
                select(User.id).where(
                    User.id == task.assigned_to,
                    User.tenant_id == self.tenant_id,
                )
            )
            if exists is None:
                raise ValueError("Task assignee does not belong to the current tenant.")
        if task.workflow_execution_id is not None:
            exists = await self.db.scalar(
                select(WorkflowExecution.id).where(
                    WorkflowExecution.id == task.workflow_execution_id,
                    WorkflowExecution.tenant_id == self.tenant_id,
                )
            )
            if exists is None:
                raise ValueError("Task workflow execution belongs to another tenant.")
        if task.workflow_step_execution_id is not None:
            parent_id = await self.db.scalar(
                select(WorkflowStepExecution.workflow_execution_id)
                .join(
                    WorkflowExecution,
                    WorkflowExecution.id == WorkflowStepExecution.workflow_execution_id,
                )
                .join(
                    WorkflowStep,
                    WorkflowStep.id == WorkflowStepExecution.workflow_step_id,
                )
                .where(
                    WorkflowStepExecution.id == task.workflow_step_execution_id,
                    WorkflowStepExecution.tenant_id == self.tenant_id,
                    WorkflowExecution.tenant_id == self.tenant_id,
                    WorkflowStep.tenant_id == self.tenant_id,
                )
            )
            if parent_id is None:
                raise ValueError(
                    "Task workflow-step execution belongs to another tenant."
                )
            if (
                task.workflow_execution_id is not None
                and parent_id != task.workflow_execution_id
            ):
                raise ValueError(
                    "Task workflow execution and step execution do not match."
                )
        if task.assignment_rule_id is not None:
            exists = await self.db.scalar(
                select(TaskAssignmentRule.id).where(
                    TaskAssignmentRule.id == task.assignment_rule_id,
                    TaskAssignmentRule.tenant_id == self.tenant_id,
                )
            )
            if exists is None:
                raise ValueError("Task assignment rule belongs to another tenant.")

    async def create(self, task: Task) -> Task:
        if task.tenant_id is not None and task.tenant_id != self.tenant_id:
            raise ValueError("Cannot create a task for another tenant.")
        await self._validate_relations(task)
        return await super().create(task)

    async def update(self, task: Task) -> Task:
        if task.tenant_id != self.tenant_id:
            raise ValueError("Task belongs to another tenant.")
        await self._validate_relations(task)
        return await super().update(task)

    async def get_by_id_for_update(self, task_id: UUID) -> Task | None:
        statement = (
            self.query()
            .where(Task.id == task_id)
            .options(selectinload(Task.status_history), selectinload(Task.comments))
            .with_for_update()
        )
        return await self.db.scalar(statement)

    async def get_detail(self, task_id: UUID) -> Task | None:
        statement = (
            self.query()
            .where(Task.id == task_id)
            .options(selectinload(Task.status_history), selectinload(Task.comments))
        )
        return await self.db.scalar(statement)

    async def list_tasks(
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
        filters = [Task.tenant_id == self.tenant_id]
        if assigned_to is not None:
            filters.append(Task.assigned_to == assigned_to)
        if status is not None:
            filters.append(Task.status == status)
        if priority is not None:
            filters.append(Task.priority == priority)
        total = int(
            await self.db.scalar(select(func.count(Task.id)).where(*filters)) or 0
        )
        rows = await self.db.scalars(
            select(Task)
            .where(*filters)
            .order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.all()), total

    async def add_status_history(
        self,
        *,
        task_id: UUID,
        changed_by: UUID,
        from_status: TaskStatus | None,
        to_status: TaskStatus,
    ) -> TaskStatusHistory:
        task_exists = await self.db.scalar(
            select(Task.id).where(
                Task.id == task_id,
                Task.tenant_id == self.tenant_id,
            )
        )
        if task_exists is None:
            raise ValueError("Task status history parent is outside this tenant.")
        user_exists = await self.db.scalar(
            select(User.id).where(
                User.id == changed_by,
                User.tenant_id == self.tenant_id,
            )
        )
        if user_exists is None:
            raise ValueError("Task status history actor is outside this tenant.")
        history = TaskStatusHistory(
            tenant_id=self.tenant_id,
            task_id=task_id,
            changed_by=changed_by,
            from_status=from_status,
            to_status=to_status,
        )
        self.db.add(history)
        await self.db.flush()
        return history

    async def add_comment(self, comment: TaskComment) -> TaskComment:
        if comment.tenant_id != self.tenant_id:
            raise ValueError("Task comment belongs to another tenant.")
        parent = await self.db.scalar(
            select(Task.id).where(
                Task.id == comment.task_id,
                Task.tenant_id == self.tenant_id,
            )
        )
        if parent is None:
            raise ValueError("Task comment parent is outside this tenant.")
        author_exists = await self.db.scalar(
            select(User.id).where(
                User.id == comment.author_id,
                User.tenant_id == self.tenant_id,
            )
        )
        if author_exists is None:
            raise ValueError("Task comment author is outside this tenant.")
        self.db.add(comment)
        await self.db.flush()
        await self.db.refresh(comment)
        return comment

    async def get_comments(self, task_id: UUID) -> list[TaskComment]:
        rows = await self.db.scalars(
            select(TaskComment)
            .where(
                TaskComment.tenant_id == self.tenant_id,
                TaskComment.task_id == task_id,
            )
            .order_by(TaskComment.created_at.asc())
        )
        return list(rows.all())
