from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.ocr.providers.factory import get_ocr_provider
from app.schemas.ocr import OCRResultResponse
from app.services.async_document_processing_service import AsyncOCRService
from app.utils.enums import UserRole
from app.utils.errors import not_found

router = APIRouter(prefix="/api/v1/documents", tags=["OCR"])


def _service(db: AsyncSession, user: dict[str, Any]) -> AsyncOCRService:
    return AsyncOCRService(db, get_ocr_provider(), UUID(user["tenant_id"]))


@router.post(
    "/{document_id}/ocr",
    response_model=APIResponse[OCRResultResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create OCR",
    description="Creates an OCR for a document.",
)
async def process_document_ocr(
    request: Request,
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="OCR")
    ),
) -> APIResponse[OCRResultResponse]:
    result = await _service(db, current_user).process_document_by_id(
        document_id=document_id,
        requested_by=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="OCR created successfully.",
        data=OCRResultResponse.model_validate(result),
    )


@router.get(
    "/{document_id}/ocr",
    response_model=APIResponse[OCRResultResponse],
    status_code=status.HTTP_200_OK,
    summary="Get OCR",
    description="Retrieve an OCR by document id.",
)
async def get_document_ocr(
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="OCR")
    ),
) -> APIResponse[OCRResultResponse]:
    result = await _service(db, current_user).get_latest_result(document_id)
    if result is None:
        raise not_found("OCR result")
    return APIResponse(
        success=True,
        message="OCR retrieved successfully.",
        data=OCRResultResponse.model_validate(result),
    )
