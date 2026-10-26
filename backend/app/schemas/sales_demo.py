"""Schemas for the isolated FinPilot sales-demo experience."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.sandbox import (
    SandboxAccountResponse,
    SandboxCustomerResponse,
    SandboxOrganizationResponse,
    SandboxUserResponse,
)


class SalesDemoRecordType(StrEnum):
    COMPLIANCE_CASE = "COMPLIANCE_CASE"
    AML_ALERT = "AML_ALERT"
    AI_RISK_RECOMMENDATION = "AI_RISK_RECOMMENDATION"
    INVESTIGATION_SUMMARY = "INVESTIGATION_SUMMARY"
    DASHBOARD = "DASHBOARD"
    REPORT = "REPORT"
    WORKFLOW = "WORKFLOW"


class SalesDemoCatalogScenario(BaseModel):
    key: str
    name: str
    description: str
    focus_areas: list[str]
    steps: list[str]


class SalesDemoRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sandbox_account_id: UUID
    customer_id: UUID | None
    record_type: SalesDemoRecordType
    scenario_key: str
    title: str
    summary: str
    data: dict[str, Any]
    created_at: datetime
    customer_external_reference: str | None = None


class SalesDemoVerificationResponse(BaseModel):
    id: UUID
    sandbox_account_id: UUID
    customer_id: UUID
    scenario: str
    status: str
    result: dict[str, Any]
    created_at: datetime
    customer_external_reference: str


class SalesDemoDashboardResponse(BaseModel):
    environment: Literal["sales_demo"] = "sales_demo"
    is_synthetic: Literal[True] = True
    external_connections_enabled: Literal[False] = False
    customer_count: int = Field(ge=0)
    individual_customer_count: int = Field(ge=0)
    business_customer_count: int = Field(ge=0)
    verification_count: int = Field(ge=0)
    verified_count: int = Field(ge=0)
    compliance_case_count: int = Field(ge=0)
    aml_alert_count: int = Field(ge=0)
    ai_recommendation_count: int = Field(ge=0)
    investigation_summary_count: int = Field(ge=0)
    workflow_scenario_count: int = Field(ge=0)
    report_count: int = Field(ge=0)
    scenario_record_count: int = Field(ge=0)
    usage_sample: dict[str, int]


class SalesDemoAccountCreateResponse(BaseModel):
    environment: Literal["sales_demo"] = "sales_demo"
    account: SandboxAccountResponse
    organization: SandboxOrganizationResponse
    developer: SandboxUserResponse
    api_key: str = Field(
        description="One-time fp_test_ key. Copy it now; it cannot be retrieved again."
    )
    sample_customers: list[SandboxCustomerResponse]
    scenario_count: int
    scenario_keys: list[str]
    dashboard_path: str = "/api/v1/sandbox/demo/dashboard"
    reset_path: str = "/api/v1/sandbox/demo/reset"
