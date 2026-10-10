from uuid import UUID

from sqlalchemy.orm import Session

from app.models.task import Task
from app.repositories.tenant_scoped_repository import (
    TenantScopedRepository,
)
from app.utils.enums import TaskPriority, TaskStatus


class TaskRepository(TenantScopedRepository[Task]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> None:
        super().__init__(
            db=db,
            model=Task,
            tenant_id=tenant_id,
        )

    def get_by_id_for_update(
        self,
        task_id: UUID,
    ) -> Task | None:
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
