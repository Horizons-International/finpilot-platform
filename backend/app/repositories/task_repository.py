from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.task import Task
from app.repositories.base_repository import BaseRepository
from app.utils.enums import TaskPriority, TaskStatus


class TaskRepository(
    BaseRepository[Task],
):
    def __init__(self, db: Session) -> None:
        super().__init__(
            db,
            Task,
        )

    def get_by_id_for_update(
        self,
        task_id: UUID,
    ) -> Task | None:
        return (
            self.db.query(Task)
            .filter(
                Task.id == task_id,
            )
            .with_for_update()
            .first()
        )

    def list_tasks(
        self,
        *,
        assigned_to: UUID | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Task], int]:
        query = self.db.query(Task)

        if assigned_to is not None:
            query = query.filter(
                Task.assigned_to == assigned_to,
            )

        if status is not None:
            query = query.filter(
                Task.status == status,
            )

        if priority is not None:
            query = query.filter(
                Task.priority == priority,
            )

        total = query.with_entities(func.count(Task.id)).scalar() or 0

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
