"""Pydantic schemas for implementation workspace APIs."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.utils.implementation_workspace_enums import (
    ImplementationMemberRole,
    ImplementationMemberType,
    ImplementationStage,
    ImplementationTaskCategory,
    ImplementationTaskPriority,
    ImplementationWorkStatus,
)


class ImplementationWorkspaceCreate(BaseModel):
    customer_tenant_id: UUID | None = None
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    start_date: date | None = None
    target_go_live_date: date | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_timeline(self) -> "ImplementationWorkspaceCreate":
        if (
            self.start_date is not None
            and self.target_go_live_date is not None
            and self.target_go_live_date < self.start_date
        ):
            raise ValueError("Target go-live date cannot be before the start date.")
        return self


class ImplementationWorkspaceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    start_date: date | None = None
    target_go_live_date: date | None = None
    actual_go_live_at: datetime | None = None
    api_setup_status: ImplementationWorkStatus | None = None
    integration_status: ImplementationWorkStatus | None = None
    testing_status: ImplementationWorkStatus | None = None
    training_status: ImplementationWorkStatus | None = None
    user_acceptance_testing_status: ImplementationWorkStatus | None = None
    go_live_readiness_status: ImplementationWorkStatus | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_timeline(self) -> "ImplementationWorkspaceUpdate":
        if (
            self.start_date is not None
            and self.target_go_live_date is not None
            and self.target_go_live_date < self.start_date
        ):
            raise ValueError("Target go-live date cannot be before the start date.")
        return self


class ImplementationWorkspaceStageUpdate(BaseModel):
    status: ImplementationStage


class ImplementationWorkspaceUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    email: str


class ImplementationWorkspaceMemberCreate(BaseModel):
    user_id: UUID
    role: ImplementationMemberRole = ImplementationMemberRole.MEMBER
    member_type: ImplementationMemberType | None = None


class ImplementationWorkspaceMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    user_id: UUID
    member_type: ImplementationMemberType
    role: ImplementationMemberRole
    invited_by: UUID | None
    created_at: datetime
    user: ImplementationWorkspaceUserResponse


class ImplementationWorkspaceMilestoneCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    due_date: date | None = None
    assigned_to: UUID | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class ImplementationWorkspaceMilestoneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    due_date: date | None = None
    assigned_to: UUID | None = None
    status: ImplementationWorkStatus | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class ImplementationWorkspaceMilestoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    title: str
    description: str | None
    due_date: date | None
    status: ImplementationWorkStatus
    assigned_to: UUID | None
    created_by: UUID | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    assigned_user: ImplementationWorkspaceUserResponse | None = None


class ImplementationWorkspaceTaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    category: ImplementationTaskCategory = ImplementationTaskCategory.PROJECT
    priority: ImplementationTaskPriority = ImplementationTaskPriority.MEDIUM
    milestone_id: UUID | None = None
    assigned_to: UUID | None = None
    due_date: date | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class ImplementationWorkspaceTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    category: ImplementationTaskCategory | None = None
    status: ImplementationWorkStatus | None = None
    priority: ImplementationTaskPriority | None = None
    milestone_id: UUID | None = None
    assigned_to: UUID | None = None
    due_date: date | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class ImplementationWorkspaceTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    milestone_id: UUID | None
    title: str
    description: str | None
    category: ImplementationTaskCategory
    status: ImplementationWorkStatus
    priority: ImplementationTaskPriority
    assigned_to: UUID | None
    due_date: date | None
    created_by: UUID | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    assigned_user: ImplementationWorkspaceUserResponse | None = None


class ImplementationWorkspaceCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    task_id: UUID | None = None

    @model_validator(mode="after")
    def ensure_nonempty_body(self) -> "ImplementationWorkspaceCommentCreate":
        self.body = self.body.strip()
        if not self.body:
            raise ValueError("Comment body cannot be empty.")
        return self


class ImplementationWorkspaceCommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    task_id: UUID | None
    author_id: UUID | None
    body: str
    created_at: datetime
    author: ImplementationWorkspaceUserResponse | None = None


class ImplementationWorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    customer_tenant_id: UUID
    title: str
    description: str | None
    status: ImplementationStage
    api_setup_status: ImplementationWorkStatus
    integration_status: ImplementationWorkStatus
    testing_status: ImplementationWorkStatus
    training_status: ImplementationWorkStatus
    user_acceptance_testing_status: ImplementationWorkStatus
    go_live_readiness_status: ImplementationWorkStatus
    start_date: date | None
    target_go_live_date: date | None
    actual_go_live_at: datetime | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    progress_percent: int


class ImplementationWorkspaceDetailResponse(ImplementationWorkspaceResponse):
    members: list[ImplementationWorkspaceMemberResponse]
    milestones: list[ImplementationWorkspaceMilestoneResponse]
    tasks: list[ImplementationWorkspaceTaskResponse]


class ImplementationWorkspaceCommentListResponse(BaseModel):
    comments: list[ImplementationWorkspaceCommentResponse]
    total: int
