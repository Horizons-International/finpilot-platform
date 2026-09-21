from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Request,
    UploadFile,
    status,
)

from app.core.dependencies import (
    get_knowledge_document_service,
)
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.knowledge_document import (
    KnowledgeDocumentResponse,
    KnowledgeDocumentStatusUpdate,
    KnowledgeDocumentVersionCreate,
)
from app.services.knowledge_document_service import (
    KnowledgeDocumentService,
)
from app.utils.enums import (
    KnowledgeDocumentCategory,
    KnowledgeDocumentStatus,
    UserRole,
)

router = APIRouter(
    prefix="/api/v1/knowledge-documents",
    tags=["Knowledge Documents"],
)


@router.post(
    "",
    response_model=APIResponse[KnowledgeDocumentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Post knowledge document",
    description="Uploads knowledge document.",
)
async def create_knowledge_document(
    request: Request,
    name: str = Form(...),
    category: KnowledgeDocumentCategory = Form(...),
    file: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="knowledge document",
        )
    ),
    service: KnowledgeDocumentService = Depends(get_knowledge_document_service),
):
    document = await service.create_document(
        name=name,
        category=category,
        file=file,
        uploaded_by=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Knowledge document uploaded successfully.",
        data=document,
    )


@router.get(
    "",
    response_model=APIResponse[list[KnowledgeDocumentResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get knowledge documents",
    description="Retrieves all knowledge documents.",
)
def list_knowledge_documents(
    service: KnowledgeDocumentService = Depends(get_knowledge_document_service),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="knowledge document",
        )
    ),
):
    documents = service.get_documents()

    return APIResponse(
        success=True,
        message="Retrieved all knowledge documents.",
        data=documents,
    )


@router.get(
    "/{document_id}",
    response_model=APIResponse[KnowledgeDocumentResponse],
    status_code=status.HTTP_200_OK,
    summary="Get knowledge document",
    description="Retrieves knowledge document by ID.",
)
def get_knowledge_document(
    document_id: UUID,
    service: KnowledgeDocumentService = Depends(get_knowledge_document_service),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="knowledge document",
        )
    ),
):
    document = service.get_document(document_id)

    return APIResponse(
        success=True,
        message="Retrieved knowledge document successfully.",
        data=document,
    )


@router.post(
    "/{document_id}/versions",
    response_model=APIResponse[KnowledgeDocumentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Post knowledge document version",
    description="Creates knowledge document version.",
)
async def create_knowledge_document_version(
    request: Request,
    document_id: UUID,
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    category: KnowledgeDocumentCategory | None = Form(
        default=None,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="knowledge document",
        )
    ),
    service: KnowledgeDocumentService = Depends(get_knowledge_document_service),
):
    data = KnowledgeDocumentVersionCreate(
        name=name,
        category=category,
    )

    document = await service.create_version(
        document_id=document_id,
        file=file,
        uploaded_by=UUID(current_user["sub"]),
        email=current_user["email"],
        data=data,
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Created knowledge document version.",
        data=document,
    )


@router.get(
    "/{document_id}/versions",
    response_model=APIResponse[list[KnowledgeDocumentResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get knowledge document versions",
    description="Retrieves all knowledge document versions.",
)
def list_knowledge_document_versions(
    document_id: UUID,
    service: KnowledgeDocumentService = Depends(get_knowledge_document_service),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="knowledge document",
        )
    ),
):
    versions = service.get_versions(document_id)

    return APIResponse(
        success=True,
        message="Retrieved all knowledge document versions",
        data=versions,
    )


@router.patch(
    "/{document_id}/status",
    response_model=APIResponse[KnowledgeDocumentResponse],
    status_code=status.HTTP_200_OK,
    summary="Update knowledge document status",
    description="Updates knowledge document status.",
)
def update_knowledge_document_status(
    request: Request,
    document_id: UUID,
    payload: KnowledgeDocumentStatusUpdate,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="knowledge document",
        )
    ),
    service: KnowledgeDocumentService = Depends(get_knowledge_document_service),
):
    if payload.status == KnowledgeDocumentStatus.ACTIVE:
        document = service.activate_document(
            document_id=document_id,
            uploaded_by=UUID(current_user["sub"]),
            email=current_user["email"],
            ip_address=(request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent"),
        )
    else:
        document = service.deactivate_document(
            document_id=document_id,
            uploaded_by=UUID(current_user["sub"]),
            email=current_user["email"],
            ip_address=(request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent"),
        )

    return APIResponse(
        success=True,
        message="Updated status of knowledge document.",
        data=document,
    )
