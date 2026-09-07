from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.verification_document_type import (
    VerificationDocumentTypeCreate,
    VerificationDocumentTypeResponse,
    VerificationDocumentTypeUpdate,
)
from app.services.verification_document_type_service import (
    VerificationDocumentTypeService,
)
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/verification-document-types",
    tags=["Verification Document Types"],
)


def get_verification_document_type_service(
    db=Depends(get_db),
) -> VerificationDocumentTypeService:
    return VerificationDocumentTypeService(db)


@router.post(
    "",
    response_model=APIResponse[VerificationDocumentTypeResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_verification_document_type(
    data: VerificationDocumentTypeCreate,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="verification_document_type",
        )
    ),
    service: VerificationDocumentTypeService = Depends(
        get_verification_document_type_service
    ),
) -> APIResponse[VerificationDocumentTypeResponse]:
    document_type = service.create(
        data=data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
    )

    return APIResponse(
        success=True,
        message="Verification document type created successfully.",
        data=VerificationDocumentTypeResponse.model_validate(document_type),
    )


@router.get(
    "",
    response_model=APIResponse[list[VerificationDocumentTypeResponse]],
)
def get_verification_document_types(
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="verification_document_type",
        )
    ),
    service: VerificationDocumentTypeService = Depends(
        get_verification_document_type_service
    ),
) -> APIResponse[list[VerificationDocumentTypeResponse]]:
    document_types = service.get_all()

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
)
def get_active_verification_document_types(
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="verification_document_type",
        )
    ),
    service: VerificationDocumentTypeService = Depends(
        get_verification_document_type_service
    ),
) -> APIResponse[list[VerificationDocumentTypeResponse]]:
    document_types = service.get_active()

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
)
def get_verification_document_type(
    document_type_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="verification_document_type",
        )
    ),
    service: VerificationDocumentTypeService = Depends(
        get_verification_document_type_service
    ),
) -> APIResponse[VerificationDocumentTypeResponse]:
    document_type = service.get_by_id(document_type_id)

    return APIResponse(
        success=True,
        message="Verification document type retrieved successfully.",
        data=VerificationDocumentTypeResponse.model_validate(document_type),
    )


@router.patch(
    "/{document_type_id}",
    response_model=APIResponse[VerificationDocumentTypeResponse],
)
def update_verification_document_type(
    document_type_id: UUID,
    data: VerificationDocumentTypeUpdate,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="verification_document_type",
        )
    ),
    service: VerificationDocumentTypeService = Depends(
        get_verification_document_type_service
    ),
) -> APIResponse[VerificationDocumentTypeResponse]:
    document_type = service.update(
        document_type_id=document_type_id,
        data=data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
    )

    return APIResponse(
        success=True,
        message="Verification document type updated successfully.",
        data=VerificationDocumentTypeResponse.model_validate(document_type),
    )
