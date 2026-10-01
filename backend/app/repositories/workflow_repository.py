from uuid import UUID

from sqlalchemy.orm import Session

from app.models.workflow import Workflow, WorkflowStep
from app.repositories.base_repository import BaseRepository
from app.utils.enums import WorkflowStatus


class WorkflowRepository(BaseRepository[Workflow]):
    def __init__(self, db: Session) -> None:
        super().__init__(
            db,
            Workflow,
        )

    def get_by_name(
        self,
        name: str,
    ) -> Workflow | None:
        return (
            self.db.query(Workflow)
            .filter(
                Workflow.name == name,
            )
            .first()
        )

    def get_all(
        self,
        *,
        status: WorkflowStatus | None = None,
    ) -> list[Workflow]:
        query = self.db.query(Workflow)

        if status is not None:
            query = query.filter(
                Workflow.status == status,
            )

        return query.order_by(
            Workflow.created_at.desc(),
        ).all()

    def get_steps(
        self,
        workflow_id: UUID,
        *,
        for_update: bool = False,
    ) -> list[WorkflowStep]:
        query = (
            self.db.query(WorkflowStep)
            .filter(
                WorkflowStep.workflow_id == workflow_id,
            )
            .order_by(
                WorkflowStep.order_number.asc(),
            )
        )

        if for_update:
            query = query.with_for_update()

        return query.all()

    def get_step(
        self,
        workflow_id: UUID,
        step_id: UUID,
        *,
        for_update: bool = False,
    ) -> WorkflowStep | None:
        query = self.db.query(WorkflowStep).filter(
            WorkflowStep.id == step_id,
            WorkflowStep.workflow_id == workflow_id,
        )

        if for_update:
            query = query.with_for_update()

        return query.first()
