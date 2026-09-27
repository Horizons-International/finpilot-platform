from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import TransactionMonitoringOutcome


class TransactionMonitoringRequest(BaseModel):
    customer_id: UUID
    transaction_id: UUID

    amount: Decimal = Field(
        gt=0,
        description="Transaction amount.",
    )

    currency: str = Field(
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
        description="ISO-style three-letter currency code.",
    )

    country: str = Field(
        min_length=1,
        max_length=100,
    )

    transaction_type: str = Field(
        min_length=1,
        max_length=100,
    )

    transaction_date: datetime


class TransactionMonitoringResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    customer_id: UUID
    rule_id: UUID
    result: TransactionMonitoringOutcome
    alert_required: bool
    created_at: datetime


class TransactionMonitoringResponse(BaseModel):
    transaction_id: UUID
    customer_id: UUID
    evaluated_rule_count: int
    matched_rule_count: int
    alerts_generated: int
    results: list[TransactionMonitoringResultResponse]
