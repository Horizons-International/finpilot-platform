from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.customer import CustomerResponse
from app.schemas.document_review import (
    DocumentReviewResponse,
    ReviewDocumentResponse,
    ReviewOCRResponse,
)
from app.schemas.extraction_review import (
    ExtractionReviewReject,
    ExtractionReviewResponse,
    ExtractionReviewUpdate,
)
from app.services.async_document_processing_service import AsyncDocumentReviewService
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/documents", tags=["Document Review"])


def _service(db: AsyncSession, user: dict[str, Any]) -> AsyncDocumentReviewService:
    return AsyncDocumentReviewService(db, UUID(user["tenant_id"]))


@router.get(
    "/{document_id}/review",
    response_model=APIResponse[DocumentReviewResponse],
    status_code=status.HTTP_200_OK,
    summary="Get document review",
    description="Retrieves document review by ID.",
)
async def get_document_review(
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="document_review",
        )
    ),
) -> APIResponse[DocumentReviewResponse]:
    document, ocr, extraction, customer = await _service(db, current_user).get_review(
        document_id
    )
    return APIResponse(
        success=True,
        message="Document review retrieved successfully.",
        data=DocumentReviewResponse(
            document=ReviewDocumentResponse.model_validate(document),
            ocr_result=ReviewOCRResponse.model_validate(ocr),
            extraction=ExtractionReviewResponse.model_validate(extraction),
            customer=CustomerResponse.model_validate(customer),
        ),
    )


@router.patch(
    "/{document_id}/review",
    response_model=APIResponse[ExtractionReviewResponse],
    status_code=status.HTTP_200_OK,
    summary="Patch document review",
    description="Updates document review.",
)
async def update_document_review(
    request: Request,
    document_id: UUID,
    data: ExtractionReviewUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="document_review",
        )
    ),
) -> APIResponse[ExtractionReviewResponse]:
    extraction = await _service(db, current_user).update_extraction(
        document_id=document_id,
        reviewer_id=UUID(current_user["sub"]),
        data=data,
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="Document extraction updated successfully.",
        data=ExtractionReviewResponse.model_validate(extraction),
    )


@router.post(
    "/{document_id}/review/approve",
    response_model=APIResponse[ExtractionReviewResponse],
    status_code=status.HTTP_200_OK,
    summary="Approve document review",
    description="Approves document review.",
)
async def approve_document_review(
    request: Request,
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="document_review",
        )
    ),
) -> APIResponse[ExtractionReviewResponse]:
    extraction = await _service(db, current_user).approve(
        document_id=document_id,
        reviewer_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="Document extraction approved successfully.",
        data=ExtractionReviewResponse.model_validate(extraction),
    )


@router.post(
    "/{document_id}/review/reject",
    response_model=APIResponse[ExtractionReviewResponse],
    status_code=status.HTTP_200_OK,
    summary="Reject document review",
    description="Rejects document review.",
)
async def reject_document_review(
    request: Request,
    document_id: UUID,
    data: ExtractionReviewReject,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="document_review",
        )
    ),
) -> APIResponse[ExtractionReviewResponse]:
    extraction = await _service(db, current_user).reject(
        document_id=document_id,
        reviewer_id=UUID(current_user["sub"]),
        reason=data.reason,
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="Document extraction rejected successfully.",
        data=ExtractionReviewResponse.model_validate(extraction),
    )
