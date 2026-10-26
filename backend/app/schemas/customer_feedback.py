"""Validation schemas for customer feedback and product roadmap items."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FeedbackCategory = Literal["FEATURE_REQUEST", "IMPROVEMENT", "PROBLEM", "COMPLAINT"]
FeedbackPriority = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
FeedbackStatus = Literal[
    "SUBMITTED",
    "UNDER_REVIEW",
    "ACCEPTED",
    "PLANNED",
    "IN_PROGRESS",
    "COMPLETED",
    "DECLINED",
    "DUPLICATE",
]
RoadmapStatus = Literal["PROPOSED", "PLANNED", "IN_PROGRESS", "SHIPPED", "DECLINED"]
RoadmapVisibility = Literal["PUBLIC", "INTERNAL"]


class CustomerFeedbackCreate(BaseModel):
    title: str = Field(min_length=4, max_length=200)
    category: FeedbackCategory
    description: str = Field(min_length=10, max_length=10000)
    roadmap_item_id: UUID | None = None

    @field_validator("title", "description")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field must not be blank.")
        return normalized


class CustomerFeedbackUpdate(BaseModel):
    status: FeedbackStatus | None = None
    priority: FeedbackPriority | None = None
    roadmap_item_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def validate_patch(self) -> "CustomerFeedbackUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        for name in ("status", "priority"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class CustomerFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    title: str
    category: FeedbackCategory
    description: str
    priority: FeedbackPriority
    status: FeedbackStatus
    submitted_by: UUID | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    roadmap_item_id: UUID | None
    roadmap_item_title: str | None = None
    created_at: datetime
    updated_at: datetime


class CustomerFeedbackHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    feedback_id: UUID
    event_type: str
    old_value: str | None
    new_value: str | None
    notes: str | None
    changed_by: UUID | None
    created_at: datetime


class ProductRoadmapItemCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: RoadmapStatus = "PROPOSED"
    visibility: RoadmapVisibility = "INTERNAL"
    target_release: str | None = Field(default=None, max_length=80)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Title must not be blank.")
        return normalized

    @field_validator("description", "target_release")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ProductRoadmapItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: RoadmapStatus | None = None
    visibility: RoadmapVisibility | None = None
    target_release: str | None = Field(default=None, max_length=80)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Title must not be blank.")
        return normalized

    @field_validator("description", "target_release")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def validate_patch(self) -> "ProductRoadmapItemUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        for name in ("title", "status", "visibility"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class ProductRoadmapItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    status: RoadmapStatus
    visibility: RoadmapVisibility
    target_release: str | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class CustomerFeedbackSummaryResponse(BaseModel):
    total_submissions: int
    awaiting_review: int
    accepted_or_planned: int
    in_progress: int
    completed: int
    declined_or_duplicate: int
    critical_or_high_priority: int
    linked_to_roadmap: int
