from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.extraction.providers.factory import get_extraction_provider
from app.schemas.document_extraction import DocumentExtractionResponse
from app.services.async_document_processing_service import (
    AsyncDocumentExtractionService,
)
from app.utils.enums import UserRole
from app.utils.errors import not_found

router = APIRouter(prefix="/api/v1/documents", tags=["Document Extraction"])


def _service(db: AsyncSession, user: dict[str, Any]) -> AsyncDocumentExtractionService:
    return AsyncDocumentExtractionService(
        db, get_extraction_provider(), UUID(user["tenant_id"])
    )


@router.post(
    "/{document_id}/extraction",
    response_model=APIResponse[DocumentExtractionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Post document extraction",
    description="Creates document extraction.",
)
async def extract_document(
    request: Request,
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="document_extraction",
        )
    ),
) -> APIResponse[DocumentExtractionResponse]:
    result = await _service(db, current_user).extract_document_by_id(
        document_id=document_id,
        requested_by=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
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
async def get_document_extraction(
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="document_extraction",
        )
    ),
) -> APIResponse[DocumentExtractionResponse]:
    result = await _service(db, current_user).get_latest_result(document_id)
    if result is None:
        raise not_found("Document extraction result")
    return APIResponse(
        success=True,
        message="Document extraction retrieved successfully.",
        data=DocumentExtractionResponse.model_validate(result),
    )
