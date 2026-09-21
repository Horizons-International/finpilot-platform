from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.core.responses import APIResponse
from app.core.security import require_roles
from app.extraction.services.dependencies import get_document_extraction_service
from app.extraction.services.extraction_service import DocumentExtractionService
from app.schemas.document_extraction import DocumentExtractionResponse
from app.utils.enums import UserRole
from app.utils.errors import not_found

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["Document Extraction"],
)


@router.post(
    "/{document_id}/extraction",
    response_model=APIResponse[DocumentExtractionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Post document extraction",
    description="Creates document extraction.",
)
def extract_document(
    request: Request,
    document_id: UUID,
    extraction_service: DocumentExtractionService = Depends(
        get_document_extraction_service
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="document_extraction",
        )
    ),
) -> APIResponse[DocumentExtractionResponse]:
    result = extraction_service.extract_document_by_id(
        document_id=document_id,
        requested_by=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Document extraction created successfully.",
        data=DocumentExtractionResponse.model_validate(result),
    )


@router.get(
    "/{document_id}/extraction",
    response_model=APIResponse[DocumentExtractionResponse],
    status_code=status.HTTP_200_OK,
    summary="Get document extraction",
    description="Retrieves document extraction by ID.",
)
def get_document_extraction(
    document_id: UUID,
    extraction_service: DocumentExtractionService = Depends(
        get_document_extraction_service
    ),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="document_extraction",
        )
    ),
) -> APIResponse[DocumentExtractionResponse]:
    result = extraction_service.get_latest_result(document_id)

    if result is None:
        raise not_found("Document extraction result")

    return APIResponse(
        success=True,
        message="Document extraction retrieved successfully.",
        data=DocumentExtractionResponse.model_validate(result),
    )
