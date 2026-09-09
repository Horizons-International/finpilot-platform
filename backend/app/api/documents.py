from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, UploadFile, status
from fastapi import File as FastAPIFile

from app.core.dependencies import get_document_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.document import (
    CustomerDocumentListResponse,
    CustomerDocumentResponse,
)
from app.services.document_service import DocumentService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/customers/{customer_id}/verification-cases/{verification_case_id}/documents",
    tags=["Customer Documents"],
)


@router.post(
    "",
    response_model=APIResponse[CustomerDocumentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload verification document",
    description="Upload a document for a customer's verification case.",
)
async def upload_document(
    customer_id: UUID,
    verification_case_id: UUID,
    document_type_id: UUID = Form(...),
    file: UploadFile = FastAPIFile(...),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="customer_document",
        )
    ),
    service: DocumentService = Depends(get_document_service),
) -> APIResponse[CustomerDocumentResponse]:
    document = await service.upload_document(
        customer_id=customer_id,
        verification_case_id=verification_case_id,
        document_type_id=document_type_id,
        file=file,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
    )

    return APIResponse(
        success=True,
        message="Document uploaded successfully.",
        data=CustomerDocumentResponse.model_validate(document),
    )


@router.get(
    "",
    response_model=APIResponse[CustomerDocumentListResponse],
    status_code=status.HTTP_200_OK,
    summary="Get verification case documents",
    description="Retrieve all documents belonging to a verification case.",
)
def get_documents(
    customer_id: UUID,
    verification_case_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="customer_document",
        )
    ),
    service: DocumentService = Depends(get_document_service),
) -> APIResponse[CustomerDocumentListResponse]:
    documents = service.get_documents_by_case(
        customer_id=customer_id,
        verification_case_id=verification_case_id,
    )

    return APIResponse(
        success=True,
        message="Documents retrieved successfully.",
        data=CustomerDocumentListResponse(
            documents=[
                CustomerDocumentResponse.model_validate(document)
                for document in documents
            ],
            total=len(documents),
        ),
    )


@router.get(
    "/{document_id}",
    response_model=APIResponse[CustomerDocumentResponse],
    status_code=status.HTTP_200_OK,
    summary="Get verification document metadata",
    description="Retrieve metadata for a verification document.",
)
def get_document(
    customer_id: UUID,
    verification_case_id: UUID,
    document_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="customer_document",
        )
    ),
    service: DocumentService = Depends(get_document_service),
) -> APIResponse[CustomerDocumentResponse]:
    document = service.get_document(
        customer_id=customer_id,
        verification_case_id=verification_case_id,
        document_id=document_id,
    )

    return APIResponse(
        success=True,
        message="Document retrieved successfully.",
        data=CustomerDocumentResponse.model_validate(document),
    )
