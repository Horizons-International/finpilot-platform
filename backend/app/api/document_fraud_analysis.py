"""Endpoints for tenant-scoped AI-assisted document fraud screening."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.document_fraud_analysis import (
    DocumentFraudAnalysisListResponse,
    DocumentFraudAnalysisRequest,
    DocumentFraudAnalysisResponse,
)
from app.services.document_fraud_analysis_service import DocumentFraudAnalysisService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/document-fraud",
    tags=["Document Fraud Analysis"],
)

_DOCUMENT_REVIEW_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_OFFICER,
)


def _service(db: Session, current_user: dict[str, Any]) -> DocumentFraudAnalysisService:
    return DocumentFraudAnalysisService(
        db,
        tenant_id=UUID(str(current_user["tenant_id"])),
    )


@router.post(
    "/documents/{document_id}/analyze",
    response_model=APIResponse[DocumentFraudAnalysisResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Analyze document authenticity indicators",
    description=(
        "Runs OCR-quality, missing-field, profile-consistency, and duplicate checks, "
        "then optionally enriches the evidence with the configured AI provider. "
        "Results are stored for human compliance review."
    ),
)
def analyze_document_fraud(
    document_id: UUID,
    payload: DocumentFraudAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_DOCUMENT_REVIEW_ROLES, resource_type="document_fraud_analysis")
    ),
) -> APIResponse[DocumentFraudAnalysisResponse]:
    result = _service(db, current_user).analyze(
        document_id,
        user_id=UUID(current_user["sub"]),
        use_ai=payload.use_ai,
    )
    return APIResponse(
        success=True,
        message="Document fraud analysis completed successfully.",
        data=result,
    )


@router.get(
    "/analyses",
    response_model=APIResponse[DocumentFraudAnalysisListResponse],
    summary="List document fraud analysis history",
)
def list_document_fraud_analyses(
    document_id: UUID | None = Query(default=None),
    customer_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_DOCUMENT_REVIEW_ROLES, resource_type="document_fraud_analysis")
    ),
) -> APIResponse[DocumentFraudAnalysisListResponse]:
    result = _service(db, current_user).list_history(
        document_id=document_id,
        customer_id=customer_id,
        limit=limit,
    )
    return APIResponse(
        success=True,
        message="Document fraud analysis history retrieved successfully.",
        data=result,
    )


@router.get(
    "/analyses/{analysis_id}",
    response_model=APIResponse[DocumentFraudAnalysisResponse],
    summary="Get a document fraud analysis",
)
def get_document_fraud_analysis(
    analysis_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_DOCUMENT_REVIEW_ROLES, resource_type="document_fraud_analysis")
    ),
) -> APIResponse[DocumentFraudAnalysisResponse]:
    result = _service(db, current_user).get_history_item(analysis_id)
    return APIResponse(
        success=True,
        message="Document fraud analysis retrieved successfully.",
        data=result,
    )
