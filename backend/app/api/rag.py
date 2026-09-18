from fastapi import APIRouter, Depends

from app.core.dependencies import (
    get_current_user,
    get_retrieval_service,
)
from app.core.responses import APIResponse
from app.rag.retrieval import RetrievalService
from app.schemas.rag import (
    RetrievalRequest,
    RetrievalResponse,
)

router = APIRouter(
    prefix="/api/v1/rag",
    tags=["RAG"],
)


@router.post(
    "/retrieve",
    response_model=APIResponse[RetrievalResponse],
)
def retrieve_knowledge(
    payload: RetrievalRequest,
    current_user=Depends(get_current_user),
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
