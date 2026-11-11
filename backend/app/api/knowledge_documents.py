from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status

from app.core.async_dependencies import (
    get_async_knowledge_document_service,
    get_async_knowledge_indexing_service,
)
from app.core.async_security import require_async_roles
from app.core.responses import APIResponse
from app.schemas.knowledge_document import (
    KnowledgeDocumentResponse,
    KnowledgeDocumentStatusUpdate,
    KnowledgeDocumentVersionCreate,
)
from app.services.async_knowledge_document_service import (
    AsyncKnowledgeDocumentService,
)
from app.services.async_knowledge_indexing_service import (
    AsyncKnowledgeIndexingService,
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
        require_async_roles(
            UserRole.ADMINISTRATOR,
            resource_type="knowledge_document",
        )
    ),
    service: AsyncKnowledgeDocumentService = Depends(
        get_async_knowledge_document_service
    ),
) -> APIResponse[KnowledgeDocumentResponse]:
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
        data=KnowledgeDocumentResponse.model_validate(document),
    )


@router.get(
    "",
    response_model=APIResponse[list[KnowledgeDocumentResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get knowledge documents",
    description="Retrieves all knowledge documents.",
)
async def list_knowledge_documents(
    service: AsyncKnowledgeDocumentService = Depends(
        get_async_knowledge_document_service
    ),
    _: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            resource_type="knowledge_document",
        )
    ),
) -> APIResponse[list[KnowledgeDocumentResponse]]:
    documents = await service.get_documents()

    return APIResponse(
        success=True,
        message="Retrieved all knowledge documents.",
        data=[KnowledgeDocumentResponse.model_validate(row) for row in documents],
    )


@router.get(
    "/{document_id}",
    response_model=APIResponse[KnowledgeDocumentResponse],
    status_code=status.HTTP_200_OK,
    summary="Get knowledge document",
    description="Retrieves knowledge document by ID.",
)
async def get_knowledge_document(
    document_id: UUID,
    service: AsyncKnowledgeDocumentService = Depends(
        get_async_knowledge_document_service
    ),
    _: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            resource_type="knowledge_document",
        )
    ),
) -> APIResponse[KnowledgeDocumentResponse]:
    document = await service.get_document(document_id)

    return APIResponse(
        success=True,
        message="Retrieved knowledge document successfully.",
        data=KnowledgeDocumentResponse.model_validate(document),
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
    category: KnowledgeDocumentCategory | None = Form(default=None),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            resource_type="knowledge_document",
        )
    ),
    service: AsyncKnowledgeDocumentService = Depends(
        get_async_knowledge_document_service
    ),
) -> APIResponse[KnowledgeDocumentResponse]:
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
        data=KnowledgeDocumentResponse.model_validate(document),
    )


@router.get(
    "/{document_id}/versions",
    response_model=APIResponse[list[KnowledgeDocumentResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get knowledge document versions",
    description="Retrieves all knowledge document versions.",
)
async def list_knowledge_document_versions(
    document_id: UUID,
    service: AsyncKnowledgeDocumentService = Depends(
        get_async_knowledge_document_service
    ),
    _: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            resource_type="knowledge_document",
        )
    ),
) -> APIResponse[list[KnowledgeDocumentResponse]]:
    versions = await service.get_versions(document_id)

    return APIResponse(
        success=True,
        message="Retrieved all knowledge document versions.",
        data=[KnowledgeDocumentResponse.model_validate(row) for row in versions],
    )


@router.patch(
    "/{document_id}/status",
    response_model=APIResponse[KnowledgeDocumentResponse],
    status_code=status.HTTP_200_OK,
    summary="Update knowledge document status",
    description="Updates knowledge document status.",
)
async def update_knowledge_document_status(
    request: Request,
    document_id: UUID,
    payload: KnowledgeDocumentStatusUpdate,
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            resource_type="knowledge_document",
        )
    ),
    service: AsyncKnowledgeDocumentService = Depends(
        get_async_knowledge_document_service
    ),
) -> APIResponse[KnowledgeDocumentResponse]:
    if payload.status == KnowledgeDocumentStatus.ACTIVE:
        document = await service.activate_document(
            document_id=document_id,
            uploaded_by=UUID(current_user["sub"]),
            email=current_user["email"],
            ip_address=(request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent"),
        )
    else:
        document = await service.deactivate_document(
            document_id=document_id,
            uploaded_by=UUID(current_user["sub"]),
            email=current_user["email"],
            ip_address=(request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent"),
        )

    return APIResponse(
        success=True,
        message="Updated status of knowledge document.",
        data=KnowledgeDocumentResponse.model_validate(document),
    )


@router.post(
    "/{document_id}/index",
    response_model=APIResponse[dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="Index an active knowledge document",
    description=(
        "Extracts document text, generates embeddings, and replaces the stored "
        "tenant-scoped retrieval chunks. Only active documents can be indexed."
    ),
)
async def index_knowledge_document(
    document_id: UUID,
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            resource_type="knowledge_document",
        )
    ),
    service: AsyncKnowledgeIndexingService = Depends(
        get_async_knowledge_indexing_service
    ),
) -> APIResponse[dict[str, Any]]:
    chunks = await service.index_document(
        document_id=document_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
    )

    return APIResponse(
        success=True,
        message="Knowledge document indexed successfully.",
        data={
            "document_id": str(document_id),
            "chunks_indexed": len(chunks),
        },
    )
