from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import (
    TaskAssignmentStrategy,
    UserRole,
)


class TaskAssignmentRuleConditions(BaseModel):
    role: UserRole | None = None

    department: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    country: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )


class TaskAssignmentRuleCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
    )

    workflow_id: UUID | None = None

    workflow_step_id: UUID | None = None

    conditions: TaskAssignmentRuleConditions = Field(
        default_factory=TaskAssignmentRuleConditions,
    )

    strategy: TaskAssignmentStrategy = TaskAssignmentStrategy.LEAST_LOADED

    priority: int = Field(
        default=100,
        ge=1,
        le=10000,
    )


class TaskAssignmentRuleUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
    )

    workflow_id: UUID | None = None

    workflow_step_id: UUID | None = None

    conditions: TaskAssignmentRuleConditions | None = None

    strategy: TaskAssignmentStrategy | None = None

    priority: int | None = Field(
        default=None,
        ge=1,
        le=10000,
    )


class TaskAssignmentRuleStatusUpdate(BaseModel):
    is_active: bool


class TaskAssignmentRuleResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    name: str
    description: str | None
    workflow_id: UUID | None
    workflow_step_id: UUID | None
    conditions: dict[str, Any]
    strategy: TaskAssignmentStrategy
    priority: int
    is_active: bool
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
