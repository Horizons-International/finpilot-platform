from uuid import UUID

from sqlalchemy.orm import Session

from app.models.workflow import (
    WorkflowExecution,
    WorkflowStepExecution,
)
from app.repositories.base_repository import BaseRepository
from app.utils.enums import WorkflowStepExecutionStatus


class WorkflowExecutionRepository(
    BaseRepository[WorkflowExecution],
):
    def __init__(self, db: Session) -> None:
        super().__init__(
            db,
            WorkflowExecution,
        )

    def get_by_id(
        self,
        execution_id: UUID,
    ) -> WorkflowExecution | None:
        return (
            self.db.query(WorkflowExecution)
            .filter(
                WorkflowExecution.id == execution_id,
            )
            .first()
        )

    def get_by_id_for_update(
        self,
        execution_id: UUID,
    ) -> WorkflowExecution | None:
        return (
            self.db.query(WorkflowExecution)
            .filter(
                WorkflowExecution.id == execution_id,
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
