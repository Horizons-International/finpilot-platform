from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AIModelMetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_name: str
    model_version: str
    request_count: int
    success_count: int
    error_count: int
    average_response_time_ms: float
    feedback_count: int
    average_feedback_rating: float | None
    positive_feedback_rate: float | None
    accuracy_measurement_count: int
    measured_accuracy_rate: float | None
    created_at: datetime
    updated_at: datetime


class AIModelMetricsSummaryResponse(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    error_rate: float
    average_response_time_ms: float
    feedback_count: int
    average_feedback_rating: float | None
    positive_feedback_rate: float | None
    accuracy_measurement_count: int
    measured_accuracy_rate: float | None


class AIModelFeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5, description="User rating from one to five.")
    is_accurate: bool | None = Field(
        default=None,
        description="Optional user-reported assessment of factual accuracy.",
    )
    comment: str | None = Field(default=None, max_length=4000)


class AIModelFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    interaction_id: UUID
    model_name: str
    model_version: str
    rating: int
    is_accurate: bool | None
    comment: str | None
    created_at: datetime
