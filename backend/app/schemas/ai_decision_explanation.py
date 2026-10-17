from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AIDecisionExplanationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    decision_type: str
    decision_id: UUID
    factors: list[dict[str, Any]]
    data_sources: list[dict[str, Any]]
    risk_indicators: list[dict[str, Any]]
    confidence_score: Decimal | None
    recommendation_reason: str
    model_name: str | None
    provider_name: str | None
    decision_snapshot: dict[str, Any]
    created_at: datetime


class AIDecisionExplanationHistoryResponse(BaseModel):
    items: list[AIDecisionExplanationResponse]
    total: int = Field(ge=0)
