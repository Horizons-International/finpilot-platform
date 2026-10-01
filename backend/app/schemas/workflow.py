from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import (
    UserRole,
    WorkflowExecutionStatus,
    WorkflowStatus,
    WorkflowStepExecutionStatus,
)


class WorkflowCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )


class WorkflowUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )


class WorkflowStatusUpdate(BaseModel):
    status: WorkflowStatus


class WorkflowStepCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=200,
    )

    order_number: int = Field(
        ge=1,
    )

    assigned_role: UserRole


class WorkflowStepUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    order_number: int | None = Field(
        default=None,
        ge=1,
    )

    assigned_role: UserRole | None = None


class WorkflowStepResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    workflow_id: UUID
    name: str
    order_number: int
    assigned_role: str
    created_at: datetime
    updated_at: datetime


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    name: str
    description: str | None
    status: WorkflowStatus
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowStepResponse]


class WorkflowExecutionCreate(BaseModel):
    entity_type: str = Field(
        min_length=1,
        max_length=100,
    )

    entity_id: UUID

    context: dict[str, Any] | None = None


class WorkflowExecutionCancelRequest(BaseModel):
    notes: str | None = Field(
        default=None,
        max_length=2000,
    )


class WorkflowAdvanceRequest(BaseModel):
    notes: str | None = Field(
        default=None,
        max_length=2000,
    )

    result: dict[str, Any] | None = None


class WorkflowStepExecutionResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    workflow_execution_id: UUID
    workflow_step_id: UUID
    step_name: str
    order_number: int
    assigned_role: str
    status: WorkflowStepExecutionStatus
    notes: str | None
    result: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None


class WorkflowExecutionResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    workflow_id: UUID
    entity_type: str
    entity_id: UUID
    status: WorkflowExecutionStatus
    current_step_id: UUID | None
    started_by: UUID | None
    context: dict[str, Any] | None
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    step_executions: list[WorkflowStepExecutionResponse]
