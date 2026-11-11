from typing import Any

from fastapi import APIRouter, Depends, status

from app.core.async_dependencies import get_async_retrieval_service
from app.core.async_security import require_async_roles
from app.core.responses import APIResponse
from app.rag.async_retrieval import AsyncRetrievalService
from app.schemas.rag import RetrievalRequest, RetrievalResponse
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/rag",
    tags=["RAG"],
)


@router.post(
    "/retrieve",
    response_model=APIResponse[RetrievalResponse],
    status_code=status.HTTP_200_OK,
    summary="Retrieve relevant knowledge",
    description="Retrieves relevant active knowledge for the current tenant.",
)
async def retrieve_knowledge(
    payload: RetrievalRequest,
    _: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            resource_type="ai_prompt",
        )
    ),
    service: AsyncRetrievalService = Depends(get_async_retrieval_service),
) -> APIResponse[RetrievalResponse]:
    results = await service.retrieve(
        query=payload.query,
        limit=payload.limit,
        category=payload.category,
    )

    return APIResponse(
        success=True,
        message="Retrieved relevant knowledge successfully.",
        data=RetrievalResponse(results=results),
    )
