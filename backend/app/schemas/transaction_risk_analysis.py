"""Request and response schemas for AI-assisted transaction-risk analysis."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TransactionRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TransactionRiskObservation(BaseModel):
    transaction_id: UUID
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=2)
    currency: str = Field(
        pattern=r"^[A-Z]{3}$", description="Three-letter currency code."
    )
    destination_country: str = Field(min_length=1, max_length=100)
    transaction_type: str = Field(min_length=1, max_length=100)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone.")
        return value


class TransactionRiskAnalysisRequest(BaseModel):
    customer_id: UUID
    transactions: list[TransactionRiskObservation] = Field(min_length=1, max_length=100)
    historical_transactions: list[TransactionRiskObservation] = Field(
        default_factory=list,
        max_length=500,
        description=(
            "Optional recent historical transactions from the bank's source of truth. "
            "Earlier successful analyses are also used as history."
        ),
    )

    @model_validator(mode="after")
    def require_unique_current_transaction_ids(
        self,
    ) -> "TransactionRiskAnalysisRequest":
        ids = [item.transaction_id for item in self.transactions]
        if len(ids) != len(set(ids)):
            raise ValueError("transactions contains duplicate transaction_id values.")
        historical_ids = {item.transaction_id for item in self.historical_transactions}
        if set(ids).intersection(historical_ids):
            raise ValueError(
                "A transaction_id cannot appear in "
                "both current and historical activity."
            )
        return self


class TransactionRiskAIOutput(BaseModel):
    risk_score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=5000)
    recommended_action: str = Field(min_length=1, max_length=3000)
    risk_factors: list[str] = Field(default_factory=list, max_length=30)
    confidence: float = Field(ge=0, le=1)


class TransactionRiskAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    customer_id: UUID
    created_by: UUID | None
    compliance_case_id: UUID | None
    risk_score: int
    risk_level: TransactionRiskLevel
    reason: str
    recommended_action: str
    risk_factors: list[str]
    confidence: float
    provider_name: str
    model_name: str | None
    context_snapshot: dict[str, Any]
    transaction_summary: dict[str, Any]
    baseline_summary: dict[str, Any]
    ai_response: dict[str, Any]
    created_at: datetime
