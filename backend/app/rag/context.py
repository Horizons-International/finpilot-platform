from typing import Any

from app.rag.retrieval import RetrievalService
from app.schemas.rag import RetrievalResult
from app.utils.enums import KnowledgeDocumentCategory

DEFAULT_RAG_LIMIT = 5


class RAGContextBuilder:
    """
    Builds knowledge-base context for AI requests.

    The builder keeps RAG concerns separate from the existing
    compliance/customer context service.
    """

    def __init__(
        self,
        retrieval_service: RetrievalService | None = None,
    ) -> None:
        self.retrieval_service = retrieval_service

    def build(
        self,
        *,
        query: str,
        category: KnowledgeDocumentCategory | None = None,
        limit: int = DEFAULT_RAG_LIMIT,
    ) -> dict[str, Any]:
        if self.retrieval_service is None:
            return self._empty_context(query)

        results = self.retrieval_service.retrieve(
            query=query,
            limit=limit,
            category=category,
        )

        return {
            "query": query,
            "results": [self._serialize_result(result) for result in results],
        }

    @staticmethod
    def _serialize_result(
        result: RetrievalResult,
    ) -> dict[str, Any]:
        return {
            "chunk_id": str(result.chunk_id),
            "document_id": str(result.document_id),
            "document_name": result.document_name,
            "category": result.category.value,
            "version": result.version,
            "content": result.content,
            "similarity": result.similarity,
        }

    @staticmethod
    def _empty_context(
        query: str,
    ) -> dict[str, Any]:
        return {
            "query": query,
            "results": [],
        }
