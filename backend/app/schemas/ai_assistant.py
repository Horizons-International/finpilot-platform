from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import (
    AIFunction,
    AIInteractionStatus,
)


class AIComplianceRequest(BaseModel):
    ai_function: AIFunction

    question: str = Field(
        min_length=1,
        max_length=4000,
    )

    customer_id: UUID | None = None
    verification_case_id: UUID | None = None
    document_id: UUID | None = None


class AIComplianceResult(BaseModel):
    summary: str
    customer_status: str
    missing_documents: list[str]
    findings: list[str]
    recommendation: str
    confidence: float


class AIComplianceResponse(BaseModel):
    interaction_id: UUID
    ai_function: AIFunction
    prompt_id: UUID
    status: AIInteractionStatus
    provider_name: str
    model: str | None
    content: str
    result: AIComplianceResult


class AIInteractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    ai_function: AIFunction
    prompt_id: UUID
    resource_type: str
    resource_id: UUID
    question: str
    response_data: dict | None
    response_text: str | None
    provider_name: str | None
    model: str | None
    provider_request_id: str | None
    status: AIInteractionStatus
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
