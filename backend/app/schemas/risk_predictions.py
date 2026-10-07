from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RiskPredictionResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    customer_id: UUID
    model_version: str
    risk_probability: float = Field(
        ge=0,
        le=1,
    )
    features: dict
    created_at: datetime


class RiskPredictionRequest(BaseModel):
    force_recalculate: bool = False
