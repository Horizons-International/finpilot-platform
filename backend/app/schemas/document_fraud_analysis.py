"""Request and response schemas for document authenticity screening."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

RiskSeverity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
QualityAssessment = Literal["GOOD", "FAIR", "POOR", "UNASSESSABLE"]


class DocumentFraudAnalysisRequest(BaseModel):
    """Settings for one screening run."""

    use_ai: bool = True


class DocumentFraudIndicator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    severity: RiskSeverity
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1500)
    evidence: dict[str, str | None] = Field(default_factory=dict)


class DocumentFraudDuplicateMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    customer_id: UUID
    match_type: Literal["DOCUMENT_NUMBER", "OCR_TEXT"]
    detail: str = Field(min_length=1, max_length=500)


class DocumentFraudResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=6000)
    quality_assessment: QualityAssessment
    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    needs_manual_review: bool
    quality_indicators: list[DocumentFraudIndicator] = Field(max_length=30)
    missing_information: list[str] = Field(max_length=30)
    inconsistencies: list[DocumentFraudIndicator] = Field(max_length=30)
    duplicate_matches: list[DocumentFraudDuplicateMatch] = Field(max_length=30)
    ai_observations: list[str] = Field(max_length=30)
    recommended_actions: list[str] = Field(max_length=30)
    confidence: float = Field(ge=0, le=1)
    ai_enrichment_available: bool


class DocumentFraudAnalysisResponse(BaseModel):
    id: UUID
    document_id: UUID
    customer_id: UUID
    status: str
    risk_score: float
    risk_level: str
    needs_manual_review: bool
    result: DocumentFraudResult | None
    provider_name: str | None
    model_name: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class DocumentFraudAnalysisListResponse(BaseModel):
    items: list[DocumentFraudAnalysisResponse]
    total: int
