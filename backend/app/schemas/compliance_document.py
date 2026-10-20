"""Pydantic responses and request bodies for compliance documentation."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.compliance_document import (
    ComplianceApprovalStatus,
    ComplianceDocumentStatus,
)

ComplianceCategory = Literal["SECURITY", "COMPLIANCE", "OPERATIONS", "OTHER"]
EvidenceType = Literal[
    "ACCESS_CONTROL",
    "ENCRYPTION",
    "MONITORING",
    "KYC_PROCESS",
    "AML_MONITORING",
    "CASE_MANAGEMENT",
    "INCIDENT_MANAGEMENT",
    "BUSINESS_CONTINUITY",
    "CHANGE_MANAGEMENT",
    "OTHER",
]


class ComplianceDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    category: str
    version: int
    status: ComplianceDocumentStatus
    owner: UUID
    created_at: datetime
    updated_at: datetime


class ComplianceDocumentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    document_id: UUID
    version: int
    file_id: UUID
    content_sha256: str
    change_summary: str | None
    uploaded_by: UUID
    created_at: datetime


class ComplianceApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    document_id: UUID
    version: int
    status: ComplianceApprovalStatus
    requested_by: UUID
    reviewed_by: UUID | None
    request_comment: str | None
    review_comment: str | None
    created_at: datetime
    reviewed_at: datetime | None


class ComplianceEvidenceCreate(BaseModel):
    evidence_type: EvidenceType
    description: str = Field(min_length=3, max_length=4000)
    source_reference: str = Field(min_length=1, max_length=1000)
    version: int | None = Field(default=None, ge=1)
    collected_at: datetime | None = None


class ComplianceEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    document_id: UUID
    version_id: UUID | None
    evidence_type: str
    description: str
    source_reference: str
    collected_by: UUID
    collected_at: datetime
    created_at: datetime


class ComplianceApprovalComment(BaseModel):
    comment: str | None = Field(default=None, max_length=4000)
