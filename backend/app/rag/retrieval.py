from sqlalchemy.orm import Session

from app.rag.embeddings import EmbeddingService
from app.repositories.knowledge_document_chunk_repository import (
    KnowledgeDocumentChunkRepository,
)
from app.schemas.rag import RetrievalResult
from app.utils.enums import KnowledgeDocumentCategory
from app.utils.errors import bad_request

DEFAULT_RETRIEVAL_LIMIT = 5
MAX_RETRIEVAL_LIMIT = 20


class RetrievalService:
    def __init__(
        self,
        db: Session,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.repository = KnowledgeDocumentChunkRepository(db)
        self.embedding_service = (
            embedding_service if embedding_service is not None else EmbeddingService()
        )

    def retrieve(
        self,
        query: str,
        limit: int = DEFAULT_RETRIEVAL_LIMIT,
        category: KnowledgeDocumentCategory | None = None,
    ) -> list[RetrievalResult]:
        query = query.strip()

        if not query:
            raise bad_request("Retrieval query is required.")

        if limit < 1:
            raise bad_request("Retrieval limit must be greater than zero.")

        if limit > MAX_RETRIEVAL_LIMIT:
            raise bad_request(f"Retrieval limit cannot exceed {MAX_RETRIEVAL_LIMIT}.")

        query_embedding = self.embedding_service.embed_query(query)

        results = self.repository.search_similar(
            embedding=query_embedding,
            limit=limit,
            category=category,
        )

        return [
            self._build_result(
                chunk=chunk,
                distance=distance,
            )
            for chunk, distance in results
        ]

    @staticmethod
    def _build_result(
        chunk,
        distance: float,
    ) -> RetrievalResult:
        document = chunk.knowledge_document

        similarity = max(
            0.0,
            min(
                1.0,
                1.0 - distance,
            ),
        )

        return RetrievalResult(
            chunk_id=chunk.id,
            document_id=document.id,
            document_name=document.name,
            category=KnowledgeDocumentCategory(
                document.category,
            ),
            version=document.version,
            content=chunk.content,
            similarity=similarity,
        )
