"""Request and response schemas for transaction anomaly detection."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TransactionActivityInput(BaseModel):
    transaction_id: UUID
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    destination_country: str | None = Field(default=None, min_length=1, max_length=100)
    beneficiary_id: str | None = Field(default=None, min_length=1, max_length=255)
    transaction_type: str = Field(default="TRANSFER", min_length=1, max_length=100)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone.")
        return value

    @field_validator("destination_country")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @field_validator("beneficiary_id")
    @classmethod
    def normalize_beneficiary(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class TransactionAnomalyAnalysisRequest(BaseModel):
    customer_id: UUID
    transactions: list[TransactionActivityInput] = Field(min_length=1, max_length=1000)
    historical_transactions: list[TransactionActivityInput] = Field(
        default_factory=list,
        max_length=5000,
        description=(
            "Optional source-of-truth history to seed the baseline. Stored activity "
            "and earlier AI transaction-risk analyses are also used where available."
        ),
    )

    @model_validator(mode="after")
    def validate_transaction_ids(self) -> "TransactionAnomalyAnalysisRequest":
        current_ids = [item.transaction_id for item in self.transactions]
        if len(current_ids) != len(set(current_ids)):
            raise ValueError("transactions contains duplicate transaction_id values.")
        historical_id_list = [
            item.transaction_id for item in self.historical_transactions
        ]
        if len(historical_id_list) != len(set(historical_id_list)):
            raise ValueError(
                "historical_transactions contains duplicate transaction_id values."
            )
        historical_ids = set(historical_id_list)
        if set(current_ids).intersection(historical_ids):
            raise ValueError(
                "A transaction_id cannot appear "
                "in both current and historical activity."
            )
        return self


class TransactionAnomalyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    customer_id: UUID
    transaction_id: UUID
    anomaly_type: str
    risk_score: float = Field(ge=0, le=100)
    risk_level: str
    summary: str
    details: dict[str, Any]
    created_at: datetime


class TransactionAnomalyAnalysisResponse(BaseModel):
    customer_id: UUID
    transactions_analyzed: int
    anomaly_count: int
    anomalies: list[TransactionAnomalyResponse]
    message: str
