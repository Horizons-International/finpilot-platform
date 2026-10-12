from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workflow import (
    Workflow,
    WorkflowExecution,
    WorkflowStep,
    WorkflowStepExecution,
)
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import WorkflowExecutionStatus, WorkflowStepExecutionStatus


class WorkflowExecutionRepository(TenantScopedRepository[WorkflowExecution]):
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(db=db, model=WorkflowExecution, tenant_id=tenant_id)

    def create(self, execution: WorkflowExecution) -> WorkflowExecution:
        if execution.tenant_id is not None and execution.tenant_id != self.tenant_id:
            raise ValueError("Cannot create an execution for another tenant.")
        workflow_exists = self.db.scalar(
            select(Workflow.id).where(
                Workflow.id == execution.workflow_id,
                Workflow.tenant_id == self.tenant_id,
            )
        )
        if workflow_exists is None:
            raise ValueError("Workflow execution parent is outside this tenant.")
        if execution.started_by is not None:
            user_exists = self.db.scalar(
                select(User.id).where(
                    User.id == execution.started_by,
                    User.tenant_id == self.tenant_id,
                )
            )
            if user_exists is None:
                raise ValueError("Workflow execution actor is outside this tenant.")
        return super().create(execution)

    def get_by_id_for_update(self, execution_id: UUID) -> WorkflowExecution | None:
        return (
            self.query()
            .filter(WorkflowExecution.id == execution_id)
            .with_for_update()
            .first()
        )

    def get_step_executions(self, execution_id: UUID) -> list[WorkflowStepExecution]:
        statement = (
            select(WorkflowStepExecution)
            .where(
                WorkflowStepExecution.tenant_id == self.tenant_id,
                WorkflowStepExecution.workflow_execution_id == execution_id,
            )
            .order_by(WorkflowStepExecution.order_number.asc())
        )
        return list(self.db.scalars(statement).all())

    def get_in_progress_step(self, execution_id: UUID) -> WorkflowStepExecution | None:
        statement = select(WorkflowStepExecution).where(
            WorkflowStepExecution.tenant_id == self.tenant_id,
            WorkflowStepExecution.workflow_execution_id == execution_id,
            WorkflowStepExecution.status == WorkflowStepExecutionStatus.IN_PROGRESS,
        )
        return self.db.scalars(statement).first()

    def has_execution_for_workflow(self, workflow_id: UUID) -> bool:
        return (
            self.db.scalar(
                select(WorkflowExecution.id)
                .where(
                    WorkflowExecution.tenant_id == self.tenant_id,
                    WorkflowExecution.workflow_id == workflow_id,
                )
                .limit(1)
            )
            is not None
        )

    def create_step_execution(
        self,
        step_execution: WorkflowStepExecution,
    ) -> WorkflowStepExecution:
        if (
            step_execution.tenant_id is not None
            and step_execution.tenant_id != self.tenant_id
        ):
            raise ValueError(
                "Cannot create a workflow step execution for another tenant."
            )

        parent_exists = self.db.scalar(
            select(WorkflowExecution.id).where(
                WorkflowExecution.id == step_execution.workflow_execution_id,
                WorkflowExecution.tenant_id == self.tenant_id,
            )
        )
        if parent_exists is None:
            raise ValueError("Workflow step execution parent is outside this tenant.")

        step_exists = self.db.scalar(
            select(WorkflowStep.id).where(
                WorkflowStep.id == step_execution.workflow_step_id,
                WorkflowStep.tenant_id == self.tenant_id,
            )
        )
        if step_exists is None:
            raise ValueError("Workflow step definition is outside this tenant.")

        step_execution.tenant_id = self.tenant_id
        self.db.add(step_execution)
        self.db.flush()
        self.db.refresh(step_execution)
        return step_execution

    def get_for_entity(
        self,
        *,
        workflow_id: UUID,
        entity_type: str,
        entity_id: UUID,
        statuses: set[WorkflowExecutionStatus] | None = None,
    ) -> WorkflowExecution | None:
        query = self.query().filter(
            WorkflowExecution.workflow_id == workflow_id,
            WorkflowExecution.entity_type == entity_type,
            WorkflowExecution.entity_id == entity_id,
        )
        if statuses:
            query = query.filter(WorkflowExecution.status.in_(statuses))
        return query.order_by(WorkflowExecution.created_at.desc()).first()

    def get_latest_for_entity(
        self,
        *,
        workflow_id: UUID,
        entity_type: str,
        entity_id: UUID,
    ) -> WorkflowExecution | None:
        return self.get_for_entity(
            workflow_id=workflow_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    def get_active_for_entity(
        self,
        *,
        workflow_id: UUID,
        entity_type: str,
        entity_id: UUID,
    ) -> WorkflowExecution | None:
        return self.get_for_entity(
            workflow_id=workflow_id,
            entity_type=entity_type,
            entity_id=entity_id,
            statuses={
                WorkflowExecutionStatus.IN_PROGRESS,
                WorkflowExecutionStatus.FAILED,
            },
        )
