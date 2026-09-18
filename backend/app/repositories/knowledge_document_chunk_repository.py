from uuid import UUID

from sqlalchemy.orm import Session

from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_chunk import KnowledgeDocumentChunk
from app.repositories.base_repository import BaseRepository
from app.utils.enums import (
    KnowledgeDocumentCategory,
    KnowledgeDocumentStatus,
)


class KnowledgeDocumentChunkRepository(BaseRepository[KnowledgeDocumentChunk]):
    def __init__(self, db: Session) -> None:
        super().__init__(
            db,
            KnowledgeDocumentChunk,
        )

    def get_by_document_id(
        self,
        document_id: UUID,
    ) -> list[KnowledgeDocumentChunk]:
        return (
            self.db.query(KnowledgeDocumentChunk)
            .filter(KnowledgeDocumentChunk.knowledge_document_id == document_id)
            .order_by(KnowledgeDocumentChunk.chunk_index)
            .all()
        )

    def delete_by_document_id(
        self,
        document_id: UUID,
    ) -> None:
        (
            self.db.query(KnowledgeDocumentChunk)
            .filter(KnowledgeDocumentChunk.knowledge_document_id == document_id)
            .delete(
                synchronize_session=False,
            )
        )

    def search_similar(
        self,
        embedding: list[float],
        limit: int,
        category: KnowledgeDocumentCategory | None = None,
    ) -> list[tuple[KnowledgeDocumentChunk, float]]:
        distance = KnowledgeDocumentChunk.embedding.cosine_distance(embedding).label(
            "distance"
        )

        query = (
            self.db.query(
                KnowledgeDocumentChunk,
                distance,
            )
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeDocumentChunk.knowledge_document_id,
            )
            .filter(
                KnowledgeDocument.status == KnowledgeDocumentStatus.ACTIVE,
            )
        )

        if category is not None:
            query = query.filter(
                KnowledgeDocument.category == category.value,
            )

        results = query.order_by(distance).limit(limit).all()

        return [(chunk, float(distance_value)) for chunk, distance_value in results]
