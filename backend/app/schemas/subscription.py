"""Request and response schemas for commercial subscriptions."""

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils.enums import SubscriptionStatus


class SubscriptionPlan(StrEnum):
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class SubscriptionCreate(BaseModel):
    tenant_id: UUID
    plan_name: SubscriptionPlan = SubscriptionPlan.STARTER
    start_date: date | None = None
    end_date: date | None = None
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    usage_limits: dict[str, int | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dates(self) -> "SubscriptionCreate":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class SubscriptionUpdate(BaseModel):
    plan_name: SubscriptionPlan | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: SubscriptionStatus | None = None
    usage_limits: dict[str, int | None] | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "SubscriptionUpdate":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    organization_name: str
    plan_name: str
    status: SubscriptionStatus
    start_date: date
    end_date: date
    usage_limits: dict[str, int | None]
    features: dict[str, bool]
    created_at: datetime
    updated_at: datetime


class SubscriptionPlanResponse(BaseModel):
    plan_name: SubscriptionPlan
    usage_limits: dict[str, int | None]
    features: dict[str, bool]


class SubscriptionUsageMetric(BaseModel):
    metric: str
    used: int
    limit: int | None
    remaining: int | None
    unit: str


class SubscriptionUsageResponse(BaseModel):
    tenant_id: UUID
    subscription_id: UUID
    plan_name: str
    status: SubscriptionStatus
    period_start: date
    period_end: date
    metrics: list[SubscriptionUsageMetric]
