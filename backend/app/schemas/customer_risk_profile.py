from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import CustomerRiskLevel


class CustomerRiskProfileCreate(BaseModel):
    customer_id: UUID
    risk_level: CustomerRiskLevel
    risk_score: int
    risk_category: str = Field(
        min_length=1,
        max_length=100,
    )
    assessed_at: datetime
    assessment_source: str = Field(
        min_length=1,
        max_length=100,
    )


class CustomerRiskProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    risk_level: CustomerRiskLevel
    risk_score: int
    risk_category: str
    assessed_at: datetime
    assessment_source: str


class CustomerRiskProfileSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    risk_level: CustomerRiskLevel
    risk_score: int
    risk_category: str
    assessed_at: datetime
    assessment_source: str
