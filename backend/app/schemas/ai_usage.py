from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AIUsageLogResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    user_id: UUID
    feature: str
    model: str
    input_tokens: int
    output_tokens: int
    response_time: int
    error_message: str | None
    created_at: datetime


class AIUsageListResponse(BaseModel):
    items: list[AIUsageLogResponse]
    total: int


class AIUsageSummaryResponse(BaseModel):
    total_requests: int
    total_errors: int
    successful_requests: int

    total_input_tokens: int
    total_output_tokens: int

    average_response_time: float


class AIUsageQuery(BaseModel):
    limit: int = Field(
        default=100,
        ge=1,
        le=500,
    )

    feature: str | None = None

    user_id: UUID | None = None
