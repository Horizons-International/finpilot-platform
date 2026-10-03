from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import SLAStatus, TaskPriority, TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=255,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    assigned_to: UUID | None = None

    priority: TaskPriority = TaskPriority.MEDIUM

    due_date: datetime | None = None

    workflow_execution_id: UUID | None = None

    workflow_step_execution_id: UUID | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    priority: TaskPriority | None = None

    due_date: datetime | None = None


class TaskAssignRequest(BaseModel):
    assigned_to: UUID


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskCommentCreate(BaseModel):
    comment: str = Field(
        min_length=1,
        max_length=5000,
    )


class TaskStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    task_id: UUID
    changed_by: UUID | None
    from_status: TaskStatus | None
    to_status: TaskStatus
    changed_at: datetime


class TaskCommentResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    task_id: UUID
    author_id: UUID | None
    comment: str
    created_at: datetime


class TaskResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    title: str
    description: str | None
    assigned_to: UUID | None
    assignment_rule_id: UUID | None
    priority: TaskPriority
    status: TaskStatus
    due_date: datetime | None
    completed_at: datetime | None
    sla_status: SLAStatus | None
    workflow_execution_id: UUID | None
    workflow_step_execution_id: UUID | None
    created_at: datetime
    updated_at: datetime


class TaskDetailResponse(TaskResponse):
    status_history: list[TaskStatusHistoryResponse]
    comments: list[TaskCommentResponse]


class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
