"""Response schemas for tenant-scoped product usage analytics."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class ProductFeatureUsage(BaseModel):
    feature_key: str
    feature_name: str
    request_count: int = Field(ge=0)


class CustomerProductUsageSummary(BaseModel):
    tenant_id: UUID
    tenant_name: str
    active_users: int = Field(
        ge=0, description="Distinct users active during the range"
    )
    login_count: int = Field(ge=0)
    api_calls: int = Field(ge=0)
    verification_requests: int = Field(ge=0)
    ai_requests: int = Field(ge=0)
    workflow_runs: int = Field(ge=0)
    report_exports: int = Field(ge=0)
    features: list[ProductFeatureUsage]
    most_used_features: list[ProductFeatureUsage]
    unused_features: list[str]


class ProductUsageDashboardResponse(BaseModel):
    start_date: date
    end_date: date
    tenant_filter: UUID | None
    total_customers: int = Field(ge=0)
    active_users: int = Field(ge=0)
    login_count: int = Field(ge=0)
    api_calls: int = Field(ge=0)
    verification_requests: int = Field(ge=0)
    ai_requests: int = Field(ge=0)
    workflow_runs: int = Field(ge=0)
    report_exports: int = Field(ge=0)
    customers: list[CustomerProductUsageSummary]


class ProductUsageFeatureReport(BaseModel):
    start_date: date
    end_date: date
    tenant_filter: UUID | None
    features: list[ProductFeatureUsage]
    most_used_features: list[ProductFeatureUsage]
    unused_features: list[str]
