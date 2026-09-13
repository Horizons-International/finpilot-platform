from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.responses import APIResponse
from app.core.security import require_roles
from app.ocr.services.dependencies import get_ocr_service
from app.ocr.services.ocr_service import OCRService
from app.schemas.ocr import OCRResultResponse
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["OCR"],
)


@router.post(
    "/{document_id}/ocr",
    response_model=APIResponse[OCRResultResponse],
    status_code=status.HTTP_201_CREATED,
)
def process_document_ocr(
    document_id: UUID,
    ocr_service: OCRService = Depends(get_ocr_service),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="OCR",
        )
    ),
) -> APIResponse[OCRResultResponse]:
    result = ocr_service.process_document_by_id(
        document_id=document_id,
        requested_by=UUID(current_user["sub"]),
    )

    return APIResponse(
        success=True,
        message="OCR created successfully.",
        data=OCRResultResponse.model_validate(result),
    )


@router.get(
    "/{document_id}/ocr",
    response_model=APIResponse[OCRResultResponse],
)
def get_document_ocr(
    document_id: UUID,
    ocr_service: OCRService = Depends(get_ocr_service),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="OCR",
        )
    ),
) -> APIResponse[OCRResultResponse]:
    result = ocr_service.get_latest_result(document_id)

    if result is None:
        from app.utils.errors import not_found

        raise not_found("OCR result")

    return APIResponse(
        success=True,
        message="OCR retrieved successfully.",
        data=OCRResultResponse.model_validate(result),
    )
