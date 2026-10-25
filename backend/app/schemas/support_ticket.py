"""Validated API payloads for customer support tickets."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
)

TicketStatus = Literal[
    "OPEN", "ASSIGNED", "IN_PROGRESS", "WAITING_CUSTOMER", "RESOLVED", "CLOSED"
]
TicketCategory = Literal[
    "API_ISSUE",
    "INTEGRATION_PROBLEM",
    "SYSTEM_ERROR",
    "CONFIGURATION_REQUEST",
    "USER_ACCESS_REQUEST",
    "REPORTING_REQUEST",
    "OTHER",
]
TicketPriority = Literal["LOW", "MEDIUM", "HIGH", "URGENT"]


class SupportTicketCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5, max_length=20000)
    category: TicketCategory = "OTHER"
    priority: TicketPriority = "MEDIUM"

    @field_validator("title", "description")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("This field must not be blank.")
        return result


class SupportTicketAssignmentUpdate(BaseModel):
    assigned_to: UUID | None


class SupportTicketStatusUpdate(BaseModel):
    status: TicketStatus


class SupportTicketCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=20000)
    is_internal: bool = False

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("Comment must not be blank.")
        return result


class SupportTicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    assigned_to: UUID | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolution_time_seconds(self) -> int | None:
        if self.resolved_at is None:
            return None
        created_at = self.created_at
        resolved_at = self.resolved_at
        if created_at.tzinfo is None and resolved_at.tzinfo is not None:
            created_at = created_at.replace(tzinfo=resolved_at.tzinfo)
        elif created_at.tzinfo is not None and resolved_at.tzinfo is None:
            resolved_at = resolved_at.replace(tzinfo=created_at.tzinfo)
        return max(0, int((resolved_at - created_at).total_seconds()))


class SupportTicketCommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    ticket_id: UUID
    author_id: UUID | None
    body: str
    is_internal: bool
    created_at: datetime


class SupportTicketAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    ticket_id: UUID
    original_filename: str
    content_type: str
    file_size: int
    uploaded_by: UUID | None
    created_at: datetime


class SupportTicketHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    ticket_id: UUID
    actor_id: UUID | None
    event_type: str
    previous_value: str | None
    new_value: str | None
    details: str | None
    created_at: datetime


class SupportTicketListFilters(BaseModel):
    status: TicketStatus | None = None
    category: TicketCategory | None = None
    priority: TicketPriority | None = None
