from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workflow import (
    Workflow,
    WorkflowExecution,
    WorkflowStepExecution,
)
from app.repositories.base_repository import BaseRepository
from app.utils.enums import WorkflowExecutionStatus, WorkflowStepExecutionStatus


class WorkflowExecutionRepository(
    BaseRepository[WorkflowExecution],
):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> None:
        super().__init__(
            db,
            WorkflowExecution,
        )
        self.tenant_id = tenant_id

    def get_by_id(
        self,
        execution_id: UUID,
    ) -> WorkflowExecution | None:
        return (
            self.db.query(WorkflowExecution)
            .join(
                Workflow,
                Workflow.id == WorkflowExecution.workflow_id,
            )
            .filter(
                WorkflowExecution.id == execution_id,
                Workflow.tenant_id == self.tenant_id,
            )
            .first()
        )

    def get_by_id_for_update(
        self,
        execution_id: UUID,
    ) -> WorkflowExecution | None:
        return (
            self.db.query(WorkflowExecution)
            .join(
                Workflow,
                Workflow.id == WorkflowExecution.workflow_id,
            )
            .filter(
                WorkflowExecution.id == execution_id,
                Workflow.tenant_id == self.tenant_id,
            )
            .with_for_update()
            .first()
        )

    def get_step_executions(
        self,
        execution_id: UUID,
    ) -> list[WorkflowStepExecution]:
        return (
            self.db.query(WorkflowStepExecution)
            .filter(
                WorkflowStepExecution.workflow_execution_id == execution_id,
            )
            .order_by(
                WorkflowStepExecution.order_number.asc(),
            )
            .all()
        )

    def get_in_progress_step(
        self,
        execution_id: UUID,
    ) -> WorkflowStepExecution | None:
        return (
            self.db.query(WorkflowStepExecution)
            .filter(
                WorkflowStepExecution.workflow_execution_id == execution_id,
                WorkflowStepExecution.status == WorkflowStepExecutionStatus.IN_PROGRESS,
            )
            .first()
        )

    def has_execution_for_workflow(
        self,
        workflow_id: UUID,
    ) -> bool:
        return (
            self.db.query(WorkflowExecution.id)
            .filter(
                WorkflowExecution.workflow_id == workflow_id,
            )
            .first()
            is not None
        )

    def create_step_execution(
        self,
        step_execution: WorkflowStepExecution,
    ) -> WorkflowStepExecution:
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
        query = select(WorkflowExecution).where(
            WorkflowExecution.workflow_id == workflow_id,
            WorkflowExecution.entity_type == entity_type,
            WorkflowExecution.entity_id == entity_id,
        )

        if statuses:
            query = query.where(
                WorkflowExecution.status.in_(statuses),
            )

        query = query.order_by(
            WorkflowExecution.created_at.desc(),
        )

        return self.db.scalars(query).first()

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
