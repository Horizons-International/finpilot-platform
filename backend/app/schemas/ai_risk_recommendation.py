"""API schemas for AI-assisted compliance risk recommendations."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AIRiskRecommendationGenerateRequest(BaseModel):
    customer_id: UUID
    compliance_case_id: UUID | None = None


class AIRiskRecommendationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    customer_id: UUID
    compliance_case_id: UUID | None
    created_by: UUID | None
    risk_score: Decimal
    risk_level: str
    recommendation: str
    reason: str
    suggested_action: str
    required_review_type: str
    risk_factors: list[str]
    confidence: float
    input_snapshot: dict[str, Any]
    provider_name: str
    model_name: str | None
    created_at: datetime


class AIRiskRecommendationHistoryResponse(BaseModel):
    items: list[AIRiskRecommendationResponse]
    total: int


class AIRiskRecommendationListQuery(BaseModel):
    customer_id: UUID | None = None
    compliance_case_id: UUID | None = None
    limit: int = Field(default=50, ge=1, le=200)
