"""Pydantic request and response models for customer success."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AccountStatus = Literal["TRIAL", "ACTIVE", "AT_RISK", "PAUSED", "CHURNED"]
ImplementationStage = Literal[
    "NOT_STARTED",
    "CONFIGURATION",
    "INTEGRATION",
    "TESTING",
    "READY_FOR_PRODUCTION",
    "LIVE",
]
HealthBand = Literal["HEALTHY", "NEEDS_ATTENTION", "AT_RISK"]
SupportCategory = Literal[
    "INCIDENT", "QUESTION", "REQUEST", "BILLING", "INTEGRATION", "TRAINING", "OTHER"
]
SupportSeverity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
SupportStatus = Literal["OPEN", "IN_PROGRESS", "WAITING_CUSTOMER", "RESOLVED", "CLOSED"]


class CustomerSuccessProfileCreate(BaseModel):
    customer_tenant_id: UUID
    account_status: AccountStatus = "TRIAL"
    implementation_stage: ImplementationStage = "NOT_STARTED"
    assigned_manager_id: UUID | None = None
    success_plan: str | None = Field(default=None, max_length=10000)
    last_contacted_at: datetime | None = None

    @field_validator("success_plan")
    @classmethod
    def normalize_success_plan(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class CustomerSuccessProfileUpdate(BaseModel):
    account_status: AccountStatus | None = None
    implementation_stage: ImplementationStage | None = None
    assigned_manager_id: UUID | None = None
    success_plan: str | None = Field(default=None, max_length=10000)
    last_contacted_at: datetime | None = None

    @field_validator("success_plan")
    @classmethod
    def normalize_success_plan(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def require_an_update(self) -> "CustomerSuccessProfileUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        for field in ("account_status", "implementation_stage"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self


class CustomerSuccessProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    customer_tenant_id: UUID
    customer_tenant_name: str | None
    account_status: AccountStatus
    implementation_stage: ImplementationStage
    assigned_manager_id: UUID | None
    assigned_manager_name: str | None
    success_plan: str | None
    last_contacted_at: datetime | None
    health_score: int = Field(ge=0, le=100)
    health_band: HealthBand
    health_score_updated_at: datetime
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class CustomerSuccessUsageSnapshotCreate(BaseModel):
    period_start: date
    period_end: date
    active_users: int = Field(ge=0)
    licensed_users: int = Field(ge=0)
    api_calls: int = Field(ge=0)
    api_call_limit: int | None = Field(default=None, ge=0)
    active_features: int = Field(default=0, ge=0)
    available_features: int = Field(default=0, ge=0)
    source: Literal["MANUAL", "BILLING_EXPORT", "API_REPORT", "SUBSCRIPTION_IMPORT"] = (
        "MANUAL"
    )

    @model_validator(mode="after")
    def validate_counts_and_period(self) -> "CustomerSuccessUsageSnapshotCreate":
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start.")
        if self.active_users > self.licensed_users:
            raise ValueError("active_users cannot exceed licensed_users.")
        if self.active_features > self.available_features:
            raise ValueError("active_features cannot exceed available_features.")
        return self


class CustomerSuccessUsageSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    profile_id: UUID
    period_start: date
    period_end: date
    active_users: int
    licensed_users: int
    api_calls: int
    api_call_limit: int | None
    active_features: int
    available_features: int
    source: str
    recorded_by: UUID | None
    created_at: datetime


class CustomerSuccessSupportInteractionCreate(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    category: SupportCategory = "QUESTION"
    severity: SupportSeverity = "MEDIUM"
    status: SupportStatus = "OPEN"
    assigned_to: UUID | None = None

    @field_validator("subject")
    @classmethod
    def normalize_subject(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Subject must not be blank.")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class CustomerSuccessSupportInteractionUpdate(BaseModel):
    severity: SupportSeverity | None = None
    status: SupportStatus | None = None
    assigned_to: UUID | None = None
    resolution_notes: str | None = Field(default=None, max_length=10000)

    @field_validator("resolution_notes")
    @classmethod
    def normalize_resolution_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def require_an_update(self) -> "CustomerSuccessSupportInteractionUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        for field in ("severity", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self


class CustomerSuccessSupportInteractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    profile_id: UUID
    subject: str
    description: str | None
    category: SupportCategory
    severity: SupportSeverity
    status: SupportStatus
    assigned_to: UUID | None
    resolution_notes: str | None
    created_by: UUID | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CustomerSuccessNoteCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    details: str = Field(min_length=1, max_length=10000)

    @field_validator("title", "details")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field must not be blank.")
        return normalized


class CustomerSuccessHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    profile_id: UUID
    event_type: str
    title: str
    details: str | None
    event_data: dict[str, object]
    actor_id: UUID | None
    created_at: datetime


class CustomerSuccessSummaryResponse(BaseModel):
    total_accounts: int
    healthy_accounts: int
    accounts_needing_attention: int
    at_risk_accounts: int
    churned_accounts: int
