"""Endpoints for tenant-scoped AI-assisted document fraud screening."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.document_fraud_analysis import (
    DocumentFraudAnalysisListResponse,
    DocumentFraudAnalysisRequest,
    DocumentFraudAnalysisResponse,
)
from app.services.async_document_processing_service import (
    AsyncDocumentFraudAnalysisService,
)
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/document-fraud", tags=["Document Fraud Analysis"])
_DOCUMENT_REVIEW_ROLES = (UserRole.ADMINISTRATOR, UserRole.COMPLIANCE_OFFICER)


def _service(
    db: AsyncSession, user: dict[str, Any]
) -> AsyncDocumentFraudAnalysisService:
    return AsyncDocumentFraudAnalysisService(db, UUID(str(user["tenant_id"])))


@router.post(
    "/documents/{document_id}/analyze",
    response_model=APIResponse[DocumentFraudAnalysisResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Analyze document authenticity indicators",
    description=(
        "Runs OCR-quality, missing-field, profile-consistency, and duplicate "
        "checks, then optionally enriches the evidence with the configured "
        "AI provider. Results are stored for human compliance review."
    ),
)
async def analyze_document_fraud(
    document_id: UUID,
    payload: DocumentFraudAnalysisRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            *_DOCUMENT_REVIEW_ROLES, resource_type="document_fraud_analysis"
        )
    ),
) -> APIResponse[DocumentFraudAnalysisResponse]:
    result = await _service(db, current_user).analyze(
        document_id, user_id=UUID(current_user["sub"]), use_ai=payload.use_ai
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
async def list_document_fraud_analyses(
    document_id: UUID | None = Query(default=None),
    customer_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            *_DOCUMENT_REVIEW_ROLES, resource_type="document_fraud_analysis"
        )
    ),
) -> APIResponse[DocumentFraudAnalysisListResponse]:
    result = await _service(db, current_user).list_history(
        document_id=document_id, customer_id=customer_id, limit=limit
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
async def get_document_fraud_analysis(
    analysis_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            *_DOCUMENT_REVIEW_ROLES, resource_type="document_fraud_analysis"
        )
    ),
) -> APIResponse[DocumentFraudAnalysisResponse]:
    result = await _service(db, current_user).get_history_item(analysis_id)
    return APIResponse(
        success=True,
        message="Document fraud analysis retrieved successfully.",
        data=result,
    )
