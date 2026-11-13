from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.verification_document_type import (
    VerificationDocumentTypeCreate,
    VerificationDocumentTypeResponse,
    VerificationDocumentTypeUpdate,
)
from app.services.async_verification_supporting_service import (
    AsyncVerificationDocumentTypeService,
)
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/verification-document-types",
    tags=["Verification Document Types"],
)


@router.post(
    "",
    response_model=APIResponse[VerificationDocumentTypeResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Post verification document type",
    description="Creates verification document type.",
)
async def create_verification_document_type(
    request: Request,
    data: VerificationDocumentTypeCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            resource_type="verification_document_type",
        )
    ),
) -> APIResponse[VerificationDocumentTypeResponse]:
    service = AsyncVerificationDocumentTypeService(db, UUID(current_user["tenant_id"]))
    document_type = await service.create(
        data=data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Verification document type created successfully.",
        data=VerificationDocumentTypeResponse.model_validate(document_type),
    )


@router.get(
    "",
    response_model=APIResponse[list[VerificationDocumentTypeResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get verification document types",
    description="Retrieves all verfication document types.",
)
async def get_verification_document_types(
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="verification_document_type",
        )
    ),
) -> APIResponse[list[VerificationDocumentTypeResponse]]:
    service = AsyncVerificationDocumentTypeService(db, UUID(_["tenant_id"]))
    document_types = await service.get_all()

    return APIResponse(
        success=True,
        message="Verification document types retrieved successfully.",
        data=[
            VerificationDocumentTypeResponse.model_validate(document_type)
            for document_type in document_types
        ],
    )


@router.get(
    "/active",
    response_model=APIResponse[list[VerificationDocumentTypeResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get active verfication  document types",
    description="Retrieves all active verification document types.",
)
async def get_active_verification_document_types(
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="verification_document_type",
        )
    ),
) -> APIResponse[list[VerificationDocumentTypeResponse]]:
    service = AsyncVerificationDocumentTypeService(db, UUID(_["tenant_id"]))
    document_types = await service.get_active()

    return APIResponse(
        success=True,
        message="Active verification document types retrieved successfully.",
        data=[
            VerificationDocumentTypeResponse.model_validate(document_type)
            for document_type in document_types
        ],
    )


@router.get(
    "/{document_type_id}",
    response_model=APIResponse[VerificationDocumentTypeResponse],
    status_code=status.HTTP_200_OK,
    summary="Get verification document type",
    description="Retrieves verifiaction document type by ID.",
)
async def get_verification_document_type(
    document_type_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="verification_document_type",
        )
    ),
) -> APIResponse[VerificationDocumentTypeResponse]:
    service = AsyncVerificationDocumentTypeService(db, UUID(_["tenant_id"]))
    document_type = await service.get_by_id(document_type_id)

    return APIResponse(
        success=True,
        message="Verification document type retrieved successfully.",
        data=VerificationDocumentTypeResponse.model_validate(document_type),
    )


@router.patch(
    "/{document_type_id}",
    response_model=APIResponse[VerificationDocumentTypeResponse],
    status_code=status.HTTP_200_OK,
    summary="Patch verification document type",
    description="Updates verification document type by ID.",
)
async def update_verification_document_type(
    request: Request,
    document_type_id: UUID,
    data: VerificationDocumentTypeUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            resource_type="verification_document_type",
        )
    ),
) -> APIResponse[VerificationDocumentTypeResponse]:
    service = AsyncVerificationDocumentTypeService(db, UUID(current_user["tenant_id"]))
    document_type = await service.update(
        document_type_id=document_type_id,
        data=data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Verification document type updated successfully.",
        data=VerificationDocumentTypeResponse.model_validate(document_type),
    )
