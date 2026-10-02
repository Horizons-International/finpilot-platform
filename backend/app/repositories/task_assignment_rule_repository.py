from uuid import UUID

from sqlalchemy.orm import Session

from app.models.task_assignment_rule import TaskAssignmentRule
from app.repositories.base_repository import BaseRepository


class TaskAssignmentRuleRepository(
    BaseRepository[TaskAssignmentRule],
):
    def __init__(self, db: Session) -> None:
        super().__init__(
            db,
            TaskAssignmentRule,
        )

    def get_by_name(
        self,
        name: str,
    ) -> TaskAssignmentRule | None:
        return (
            self.db.query(TaskAssignmentRule)
            .filter(
                TaskAssignmentRule.name == name,
            )
            .first()
        )

    def get_by_id_for_update(
        self,
        rule_id: UUID,
    ) -> TaskAssignmentRule | None:
        return (
            self.db.query(TaskAssignmentRule)
            .filter(
                TaskAssignmentRule.id == rule_id,
            )
            .with_for_update()
            .first()
        )

    def list_rules(
        self,
        *,
        is_active: bool | None = None,
        workflow_id: UUID | None = None,
        workflow_step_id: UUID | None = None,
    ) -> list[TaskAssignmentRule]:
        query = self.db.query(
            TaskAssignmentRule,
        )

        if is_active is not None:
            query = query.filter(
                TaskAssignmentRule.is_active == is_active,
            )

        if workflow_id is not None:
            query = query.filter(
                TaskAssignmentRule.workflow_id == workflow_id,
            )

        if workflow_step_id is not None:
            query = query.filter(
                TaskAssignmentRule.workflow_step_id == workflow_step_id,
            )

        return query.order_by(
            TaskAssignmentRule.priority.asc(),
            TaskAssignmentRule.created_at.asc(),
        ).all()
