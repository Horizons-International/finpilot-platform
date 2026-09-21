from typing import Any

from fastapi import APIRouter, Depends, status

from app.core.dependencies import (
    get_retrieval_service,
)
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.rag.retrieval import RetrievalService
from app.schemas.rag import (
    RetrievalRequest,
    RetrievalResponse,
)
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/rag",
    tags=["RAG"],
)


@router.post(
    "/retrieve",
    response_model=APIResponse[RetrievalResponse],
    status_code=status.HTTP_200_OK,
    summary="Get RAG",
    description="Retrieves relevent knowledge.",
)
def retrieve_knowledge(
    payload: RetrievalRequest,
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="ai_prompt",
        )
    ),
    service: RetrievalService = Depends(
        get_retrieval_service,
    ),
):
    results = service.retrieve(
        query=payload.query,
        limit=payload.limit,
        category=payload.category,
    )

    return APIResponse(
        success=True,
        message="Retrieved relevant knowledge successfully.",
        data=RetrievalResponse(
            results=results,
        ),
    )
