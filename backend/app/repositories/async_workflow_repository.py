"""Tenant-scoped async workflow definition and execution repositories."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.workflow import (
    Workflow,
    WorkflowExecution,
    WorkflowStep,
    WorkflowStepExecution,
)
from app.models.workflow_audit_log import WorkflowAuditLog
from app.repositories.async_tenant_scoped_repository import AsyncTenantScopedRepository
from app.utils.enums import WorkflowStatus, WorkflowStepExecutionStatus


class AsyncWorkflowRepository(AsyncTenantScopedRepository[Workflow]):
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(db, Workflow, tenant_id)

    async def get_by_name(self, name: str) -> Workflow | None:
        return await self.db.scalar(self.query().where(Workflow.name == name))

    async def get_workflow(self, workflow_id: UUID) -> Workflow | None:
        statement = (
            self.query()
            .where(Workflow.id == workflow_id)
            .options(selectinload(Workflow.steps))
        )
        return await self.db.scalar(statement)

    async def get_all(self, *, status: WorkflowStatus | None = None) -> list[Workflow]:
        statement = self.query().options(selectinload(Workflow.steps))
        if status is not None:
            statement = statement.where(Workflow.status == status)
        result = await self.db.scalars(statement.order_by(Workflow.created_at.desc()))
        return list(result.all())

    async def get_steps(
        self, workflow_id: UUID, *, for_update: bool = False
    ) -> list[WorkflowStep]:
        statement = (
            select(WorkflowStep)
            .join(Workflow, Workflow.id == WorkflowStep.workflow_id)
            .where(
                Workflow.tenant_id == self.tenant_id,
                WorkflowStep.tenant_id == self.tenant_id,
                Workflow.id == workflow_id,
            )
            .order_by(WorkflowStep.order_number.asc())
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.db.scalars(statement)
        return list(result.all())

    async def get_step(
        self, workflow_id: UUID, step_id: UUID, *, for_update: bool = False
    ) -> WorkflowStep | None:
        statement = (
            select(WorkflowStep)
            .join(Workflow, Workflow.id == WorkflowStep.workflow_id)
            .where(
                Workflow.tenant_id == self.tenant_id,
                WorkflowStep.tenant_id == self.tenant_id,
                Workflow.id == workflow_id,
                WorkflowStep.id == step_id,
            )
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.db.scalar(statement)

    async def has_execution(self, workflow_id: UUID) -> bool:
        value = await self.db.scalar(
            select(WorkflowExecution.id)
            .where(
                WorkflowExecution.tenant_id == self.tenant_id,
                WorkflowExecution.workflow_id == workflow_id,
            )
            .limit(1)
        )
        return value is not None


class AsyncWorkflowExecutionRepository(AsyncTenantScopedRepository[WorkflowExecution]):
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(db, WorkflowExecution, tenant_id)

    async def create(self, execution: WorkflowExecution) -> WorkflowExecution:
        if execution.tenant_id is not None and execution.tenant_id != self.tenant_id:
            raise ValueError("Cannot create an execution for another tenant.")
        workflow_id = await self.db.scalar(
            select(Workflow.id).where(
                Workflow.id == execution.workflow_id,
                Workflow.tenant_id == self.tenant_id,
            )
        )
        if workflow_id is None:
            raise ValueError("Workflow execution parent is outside this tenant.")
        if execution.started_by is not None:
            user_id = await self.db.scalar(
                select(User.id).where(
                    User.id == execution.started_by,
                    User.tenant_id == self.tenant_id,
                )
            )
            if user_id is None:
                raise ValueError("Workflow execution actor is outside this tenant.")
        return await super().create(execution)

    async def get_execution(
        self, execution_id: UUID, *, for_update: bool = False
    ) -> WorkflowExecution | None:
        statement = (
            self.query()
            .where(WorkflowExecution.id == execution_id)
            .options(selectinload(WorkflowExecution.step_executions))
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.db.scalar(statement)

    async def get_step_executions(
        self, execution_id: UUID
    ) -> list[WorkflowStepExecution]:
        result = await self.db.scalars(
            select(WorkflowStepExecution)
            .where(
                WorkflowStepExecution.tenant_id == self.tenant_id,
                WorkflowStepExecution.workflow_execution_id == execution_id,
            )
            .order_by(WorkflowStepExecution.order_number.asc())
        )
        return list(result.all())

    async def get_in_progress_step(
        self, execution_id: UUID
    ) -> WorkflowStepExecution | None:
        return await self.db.scalar(
            select(WorkflowStepExecution).where(
                WorkflowStepExecution.tenant_id == self.tenant_id,
                WorkflowStepExecution.workflow_execution_id == execution_id,
                WorkflowStepExecution.status == WorkflowStepExecutionStatus.IN_PROGRESS,
            )
        )

    async def create_step_execution(
        self, step_execution: WorkflowStepExecution
    ) -> WorkflowStepExecution:
        if (
            step_execution.tenant_id is not None
            and step_execution.tenant_id != self.tenant_id
        ):
            raise ValueError(
                "Cannot create a workflow step execution for another tenant."
            )
        parent = await self.db.scalar(
            select(WorkflowExecution.id).where(
                WorkflowExecution.id == step_execution.workflow_execution_id,
                WorkflowExecution.tenant_id == self.tenant_id,
            )
        )
        step_workflow_id = await self.db.scalar(
            select(WorkflowStep.workflow_id).where(
                WorkflowStep.id == step_execution.workflow_step_id,
                WorkflowStep.tenant_id == self.tenant_id,
            )
        )
        execution_workflow_id = await self.db.scalar(
            select(WorkflowExecution.workflow_id).where(
                WorkflowExecution.id == step_execution.workflow_execution_id,
                WorkflowExecution.tenant_id == self.tenant_id,
            )
        )
        if parent is None or step_workflow_id is None or execution_workflow_id is None:
            raise ValueError(
                "Workflow step execution parent or step is outside this tenant."
            )
        if step_workflow_id != execution_workflow_id:
            raise ValueError(
                "Workflow step does not belong to the execution's workflow."
            )
        step_execution.tenant_id = self.tenant_id
        self.db.add(step_execution)
        await self.db.flush()
        return step_execution


class AsyncWorkflowAuditLogRepository:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def create(self, audit_log: WorkflowAuditLog) -> WorkflowAuditLog:
        if audit_log.tenant_id is not None and audit_log.tenant_id != self.tenant_id:
            raise ValueError("Cannot create a workflow audit log for another tenant.")
        execution_exists = await self.db.scalar(
            select(WorkflowExecution.id).where(
                WorkflowExecution.id == audit_log.workflow_execution_id,
                WorkflowExecution.tenant_id == self.tenant_id,
            )
        )
        if execution_exists is None:
            raise ValueError("Workflow audit execution is outside this tenant.")
        if audit_log.user_id is not None:
            user_exists = await self.db.scalar(
                select(User.id).where(
                    User.id == audit_log.user_id,
                    User.tenant_id == self.tenant_id,
                )
            )
            if user_exists is None:
                raise ValueError("Workflow audit actor is outside this tenant.")
        audit_log.tenant_id = self.tenant_id
        self.db.add(audit_log)
        await self.db.flush()
        return audit_log

    async def get_by_execution_id(self, execution_id: UUID) -> list[WorkflowAuditLog]:
        result = await self.db.scalars(
            select(WorkflowAuditLog)
            .where(
                WorkflowAuditLog.tenant_id == self.tenant_id,
                WorkflowAuditLog.workflow_execution_id == execution_id,
            )
            .order_by(WorkflowAuditLog.created_at.asc(), WorkflowAuditLog.id.asc())
        )
        return list(result.all())
