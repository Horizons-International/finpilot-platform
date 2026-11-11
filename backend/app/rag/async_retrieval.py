"""Asynchronous retrieval for tenant-scoped knowledge-document chunks."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.knowledge_document_chunk import KnowledgeDocumentChunk
from app.rag.embeddings import EmbeddingService
from app.repositories.async_knowledge_document_chunk_repository import (
    AsyncKnowledgeDocumentChunkRepository,
)
from app.schemas.rag import RetrievalResult
from app.utils.enums import KnowledgeDocumentCategory
from app.utils.errors import bad_request

DEFAULT_RETRIEVAL_LIMIT = 5
MAX_RETRIEVAL_LIMIT = 20


class AsyncRetrievalService:
    """Retrieve relevant active knowledge chunks without blocking the event loop."""

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: UUID | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.repository = AsyncKnowledgeDocumentChunkRepository(
            db=db,
            tenant_id=tenant_id,
        )
        self.embedding_service = (
            embedding_service if embedding_service is not None else EmbeddingService()
        )

    async def retrieve(
        self,
        query: str,
        limit: int = DEFAULT_RETRIEVAL_LIMIT,
        category: KnowledgeDocumentCategory | None = None,
        categories: set[KnowledgeDocumentCategory] | None = None,
    ) -> list[RetrievalResult]:
        normalized_query = query.strip()
        if not normalized_query:
            raise bad_request("Retrieval query is required.")
        if limit < 1:
            raise bad_request("Retrieval limit must be greater than zero.")
        if limit > MAX_RETRIEVAL_LIMIT:
            raise bad_request(f"Retrieval limit cannot exceed {MAX_RETRIEVAL_LIMIT}.")
        if category is not None and categories is not None:
            raise bad_request("Provide category or categories, not both.")

        # OpenAI's current embedding client is synchronous. Run the network call
        # in Starlette's thread pool rather than blocking the ASGI event loop.
        query_embedding = await run_in_threadpool(
            self.embedding_service.embed_query,
            normalized_query,
        )
        results = await self.repository.search_similar(
            embedding=query_embedding,
            limit=limit,
            category=category,
            categories=categories,
        )
        return [
            self._build_result(chunk=chunk, distance=distance)
            for chunk, distance in results
        ]

    @staticmethod
    def _build_result(
        chunk: KnowledgeDocumentChunk, distance: float
    ) -> RetrievalResult:
        # The repository eagerly loads the related document. Accessing an
        # unloaded relationship here would trigger async SQLAlchemy IO from a
        # synchronous attribute access (MissingGreenlet).
        document = chunk.knowledge_document
        similarity = max(0.0, min(1.0, 1.0 - distance))
        return RetrievalResult(
            chunk_id=chunk.id,
            document_id=document.id,
            document_name=document.name,
            category=KnowledgeDocumentCategory(document.category),
            version=document.version,
            content=chunk.content,
            similarity=similarity,
        )
