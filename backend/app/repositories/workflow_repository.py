from uuid import UUID

from sqlalchemy.orm import Session

from app.models.workflow import Workflow, WorkflowStep
from app.repositories.tenant_scoped_repository import (
    TenantScopedRepository,
)
from app.utils.enums import WorkflowStatus


class WorkflowRepository(TenantScopedRepository[Workflow]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> None:
        super().__init__(
            db=db,
            model=Workflow,
            tenant_id=tenant_id,
        )

    def get_by_name(
        self,
        name: str,
    ) -> Workflow | None:
        return self.query().filter(Workflow.name == name).first()

    def get_all(
        self,
        *,
        status: WorkflowStatus | None = None,
    ) -> list[Workflow]:
        query = self.query()

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
            .join(
                Workflow,
                Workflow.id == WorkflowStep.workflow_id,
            )
            .filter(
                Workflow.tenant_id == self.tenant_id,
                Workflow.id == workflow_id,
            )
            .order_by(WorkflowStep.order_number.asc())
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
        query = (
            self.db.query(WorkflowStep)
            .join(
                Workflow,
                Workflow.id == WorkflowStep.workflow_id,
            )
            .filter(
                Workflow.tenant_id == self.tenant_id,
                Workflow.id == workflow_id,
                WorkflowStep.id == step_id,
            )
        )

        if for_update:
            query = query.with_for_update()

        return query.first()

    def get_by_id(
        self,
        workflow_id: UUID,
    ) -> Workflow | None:
        return self.query().filter(Workflow.id == workflow_id).first()
