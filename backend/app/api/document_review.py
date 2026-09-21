from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.core.dependencies import (
    get_document_review_service,
)
from app.core.responses import APIResponse
from app.core.security import require_roles
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
from app.services.document_review_service import DocumentReviewService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["Document Review"],
)


@router.get(
    "/{document_id}/review",
    response_model=APIResponse[DocumentReviewResponse],
    status_code=status.HTTP_200_OK,
    summary="Get document review",
    description="Retrieves document review by ID.",
)
def get_document_review(
    document_id: UUID,
    review_service: DocumentReviewService = Depends(
        get_document_review_service,
    ),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="document_review",
        )
    ),
) -> APIResponse[DocumentReviewResponse]:
    (
        document,
        ocr_result,
        extraction,
        customer,
    ) = review_service.get_review(document_id)

    return APIResponse(
        success=True,
        message="Document review retrieved successfully.",
        data=DocumentReviewResponse(
            document=ReviewDocumentResponse.model_validate(
                document,
            ),
            ocr_result=ReviewOCRResponse.model_validate(
                ocr_result,
            ),
            extraction=ExtractionReviewResponse.model_validate(
                extraction,
            ),
            customer=CustomerResponse.model_validate(
                customer,
            ),
        ),
    )


@router.patch(
    "/{document_id}/review",
    response_model=APIResponse[ExtractionReviewResponse],
    status_code=status.HTTP_200_OK,
    summary="Patch document review",
    description="Updates document review.",
)
def update_document_review(
    request: Request,
    document_id: UUID,
    data: ExtractionReviewUpdate,
    review_service: DocumentReviewService = Depends(
        get_document_review_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="document_review",
        )
    ),
) -> APIResponse[ExtractionReviewResponse]:
    extraction = review_service.update_extraction(
        document_id=document_id,
        reviewer_id=UUID(current_user["sub"]),
        data=data,
        email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Document extraction updated successfully.",
        data=ExtractionReviewResponse.model_validate(
            extraction,
        ),
    )


@router.post(
    "/{document_id}/review/approve",
    response_model=APIResponse[ExtractionReviewResponse],
    status_code=status.HTTP_200_OK,
    summary="Approve document review",
    description="Approves document review.",
)
def approve_document_review(
    request: Request,
    document_id: UUID,
    review_service: DocumentReviewService = Depends(
        get_document_review_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="document_review",
        )
    ),
) -> APIResponse[ExtractionReviewResponse]:
    extraction = review_service.approve(
        document_id=document_id,
        reviewer_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Document extraction approved successfully.",
        data=ExtractionReviewResponse.model_validate(
            extraction,
        ),
    )


@router.post(
    "/{document_id}/review/reject",
    response_model=APIResponse[ExtractionReviewResponse],
    status_code=status.HTTP_200_OK,
    summary="Reject document review",
    description="Rejects document review.",
)
def reject_document_review(
    request: Request,
    document_id: UUID,
    data: ExtractionReviewReject,
    review_service: DocumentReviewService = Depends(
        get_document_review_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="document_review",
        )
    ),
) -> APIResponse[ExtractionReviewResponse]:
    extraction = review_service.reject(
        document_id=document_id,
        reviewer_id=UUID(current_user["sub"]),
        reason=data.reason,
        email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Document extraction rejected successfully.",
        data=ExtractionReviewResponse.model_validate(
            extraction,
        ),
    )
