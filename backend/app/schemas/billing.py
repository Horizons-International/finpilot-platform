"""Validated request and response contracts for billing plans and invoices."""

from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PricingModel = Literal["SUBSCRIPTION", "USAGE_BASED", "ENTERPRISE"]
BillingInterval = Literal["MONTHLY", "ANNUAL", "CUSTOM"]
PlanStatus = Literal["ACTIVE", "INACTIVE"]
InvoiceStatus = Literal["DRAFT", "ISSUED", "PAID", "VOID"]
SubscriptionTier = Literal["starter", "professional", "enterprise"]
_LIMIT_KEYS = {
    "max_users",
    "api_calls",
    "verification_checks",
    "ai_requests",
    "transactions",
    "storage_bytes",
}


class BillingPlanCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    pricing_model: PricingModel
    billing_interval: BillingInterval
    subscription_tier: SubscriptionTier = "starter"
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    base_fee: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=14, decimal_places=2
    )
    unit_rates: dict[str, Decimal] = Field(default_factory=dict)
    included_units: dict[str, int] = Field(default_factory=dict)
    limits: dict[str, int | None] = Field(default_factory=dict)
    features: dict[str, bool] = Field(default_factory=dict)
    status: PlanStatus = "ACTIVE"

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError(
                "Plan name must contain at least two non-space characters."
            )
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("unit_rates")
    @classmethod
    def validate_rates(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        for metric, rate in value.items():
            if metric not in {"api_calls", "verification_checks", "ai_requests"}:
                raise ValueError(f"Unsupported billable metric: {metric}.")
            if not rate.is_finite() or rate < 0:
                raise ValueError("Rates must be finite and non-negative.")
            exponent = rate.as_tuple().exponent
            # DecimalTuple.exponent is typed as int | Literal["n", "N", "F"];
            # finite Decimal values have an integer exponent, but mypy cannot
            # infer that from Decimal.is_finite().
            if not isinstance(exponent, int) or exponent < -6:
                raise ValueError(
                    "Rates must be finite, non-negative and at most 6 decimals."
                )
        return value

    @field_validator("included_units")
    @classmethod
    def validate_included_units(cls, value: dict[str, int]) -> dict[str, int]:
        for metric, units in value.items():
            if metric not in {"api_calls", "verification_checks", "ai_requests"}:
                raise ValueError(f"Unsupported billable metric: {metric}.")
            if units < 0:
                raise ValueError("Included units must be zero or greater.")
        return value

    @field_validator("limits")
    @classmethod
    def validate_limits(cls, value: dict[str, int | None]) -> dict[str, int | None]:
        unknown = set(value) - _LIMIT_KEYS
        if unknown:
            raise ValueError(f"Unsupported limit keys: {', '.join(sorted(unknown))}.")
        for key, limit in value.items():
            if limit is not None and limit < 0:
                raise ValueError(f"Limit '{key}' must be zero or greater or null.")
        return value

    @model_validator(mode="after")
    def validate_pricing(self) -> "BillingPlanCreate":
        if self.pricing_model == "SUBSCRIPTION":
            if self.billing_interval not in {"MONTHLY", "ANNUAL"}:
                raise ValueError("Subscription plans must bill MONTHLY or ANNUAL.")
            if self.unit_rates:
                raise ValueError(
                    "SUBSCRIPTION plans cannot define usage rates; "
                    "use USAGE_BASED or ENTERPRISE."
                )
        elif self.pricing_model == "USAGE_BASED":
            if self.billing_interval != "MONTHLY":
                raise ValueError(
                    "Usage-based plans bill monthly because usage is metered monthly."
                )
            if not self.unit_rates:
                raise ValueError("USAGE_BASED plans require at least one unit rate.")
        elif self.pricing_model == "ENTERPRISE":
            if self.base_fee == 0 and not self.unit_rates:
                raise ValueError(
                    "ENTERPRISE plans require a base fee or at least one unit rate."
                )
        return self


class BillingPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    pricing_model: PricingModel | None = None
    billing_interval: BillingInterval | None = None
    subscription_tier: SubscriptionTier | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    base_fee: Decimal | None = Field(
        default=None, ge=0, max_digits=14, decimal_places=2
    )
    unit_rates: dict[str, Decimal] | None = None
    included_units: dict[str, int] | None = None
    limits: dict[str, int | None] | None = None
    features: dict[str, bool] | None = None
    status: PlanStatus | None = None

    @model_validator(mode="after")
    def require_an_update(self) -> "BillingPlanUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        for field in self.model_fields_set:
            if getattr(self, field) is None and field not in {"description"}:
                raise ValueError(f"{field} cannot be null.")
        return self


class BillingPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    pricing_model: PricingModel
    billing_interval: BillingInterval
    subscription_tier: SubscriptionTier
    currency: str
    base_fee: Decimal
    unit_rates: dict[str, Decimal]
    included_units: dict[str, int]
    limits: dict[str, int | None]
    features: dict[str, bool]
    status: PlanStatus
    created_at: datetime
    updated_at: datetime


class BillingPlanAssignmentCreate(BaseModel):
    tenant_id: UUID
    billing_plan_id: UUID
    start_date: date | None = None
    end_date: date | None = None
    usage_limit_overrides: dict[str, int | None] = Field(default_factory=dict)

    @field_validator("usage_limit_overrides")
    @classmethod
    def validate_limit_overrides(
        cls, value: dict[str, int | None]
    ) -> dict[str, int | None]:
        unknown = set(value) - _LIMIT_KEYS
        if unknown:
            raise ValueError(f"Unsupported limit keys: {', '.join(sorted(unknown))}.")
        for key, limit in value.items():
            if limit is not None and limit < 0:
                raise ValueError(f"Limit '{key}' must be zero or greater or null.")
        return value

    @model_validator(mode="after")
    def validate_dates(self) -> "BillingPlanAssignmentCreate":
        if self.start_date is not None and self.start_date.day != 1:
            raise ValueError("start_date must be the first day of a calendar month.")
        if (
            self.end_date is not None
            and self.end_date.day
            != monthrange(self.end_date.year, self.end_date.month)[1]
        ):
            raise ValueError("end_date must be the last day of a calendar month.")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        return self


class BillingPlanAssignmentResponse(BaseModel):
    tenant_id: UUID
    subscription_id: UUID
    billing_plan_id: UUID
    billing_plan_name: str
    plan_name: str
    status: str
    start_date: date
    end_date: date
    usage_limits: dict[str, int | None]
    features: dict[str, bool]


class InvoiceGenerateRequest(BaseModel):
    tenant_id: UUID
    period_start: date
    period_end: date
    due_days: int = Field(default=30, ge=0, le=180)

    @model_validator(mode="after")
    def validate_period(self) -> "InvoiceGenerateRequest":
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start.")
        if self.period_start.day != 1:
            raise ValueError("period_start must be the first day of a calendar month.")
        if (
            self.period_end.day
            != monthrange(self.period_end.year, self.period_end.month)[1]
        ):
            raise ValueError("period_end must be the last day of a calendar month.")
        return self


class InvoiceLineItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    description: str
    metric: str | None
    quantity: int
    unit_price: Decimal
    amount: Decimal
    created_at: datetime


class InvoiceResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    subscription_id: UUID
    billing_plan_id: UUID
    invoice_number: str
    plan_name_snapshot: str
    period_start: date
    period_end: date
    amount: Decimal
    currency: str
    status: InvoiceStatus
    due_date: date
    issued_at: datetime | None
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime
    is_overdue: bool = False
    line_items: list[InvoiceLineItemResponse] = Field(default_factory=list)


class InvoiceStatusUpdate(BaseModel):
    status: Literal["ISSUED", "PAID", "VOID"]
