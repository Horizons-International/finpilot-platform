"""Request and response schemas for AI-assisted AML investigations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AMLInvestigationAnalysisRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    customer_id: UUID | None = None
    compliance_case_id: UUID | None = None
    retrieval_limit: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def require_investigation_target(self) -> "AMLInvestigationAnalysisRequest":
        if self.customer_id is None and self.compliance_case_id is None:
            raise ValueError("Provide either customer_id or compliance_case_id.")
        return self


class AMLInvestigationAIResult(BaseModel):
    summary: str = Field(min_length=1, max_length=6000)
    customer_overview: str = Field(min_length=1, max_length=6000)
    risk_indicators: list[str] = Field(max_length=30)
    related_activity: list[str] = Field(max_length=30)
    suggested_actions: list[str] = Field(max_length=30)
    confidence: float = Field(ge=0, le=1)


class AMLInvestigationSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=1500)
    observed_at: datetime | None = None
    document_id: str | None = None


class AMLInvestigationAnalysisResponse(BaseModel):
    id: UUID
    customer_id: UUID | None
    compliance_case_id: UUID | None
    question: str
    status: str
    result: AMLInvestigationAIResult | None
    sources: list[AMLInvestigationSource]
    provider_name: str | None
    model_name: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class AMLInvestigationAnalysisListResponse(BaseModel):
    items: list[AMLInvestigationAnalysisResponse]
    total: int
