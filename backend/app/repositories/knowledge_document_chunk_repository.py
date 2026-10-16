from uuid import UUID

from sqlalchemy.orm import Session

from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_chunk import KnowledgeDocumentChunk
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import KnowledgeDocumentCategory, KnowledgeDocumentStatus


class KnowledgeDocumentChunkRepository(TenantScopedRepository[KnowledgeDocumentChunk]):
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        resolved_tenant_id = (
            tenant_id if tenant_id is not None else db.info.get("tenant_id")
        )
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError(
                "A tenant context is required for knowledge document chunks."
            )
        super().__init__(
            db=db,
            model=KnowledgeDocumentChunk,
            tenant_id=resolved_tenant_id,
        )

    def _validate_document(self, chunk: KnowledgeDocumentChunk) -> None:
        document_exists = (
            self.db.query(KnowledgeDocument.id)
            .filter(
                KnowledgeDocument.id == chunk.knowledge_document_id,
                KnowledgeDocument.tenant_id == self.tenant_id,
            )
            .first()
        )
        if document_exists is None:
            raise ValueError(
                "The knowledge document does not belong to the current tenant."
            )

    def create(self, chunk: KnowledgeDocumentChunk) -> KnowledgeDocumentChunk:
        self._validate_document(chunk)
        return super().create(chunk)

    def update(self, chunk: KnowledgeDocumentChunk) -> KnowledgeDocumentChunk:
        self._validate_document(chunk)
        return super().update(chunk)

    def get_by_document_id(self, document_id: UUID) -> list[KnowledgeDocumentChunk]:
        return (
            self.query()
            .filter(KnowledgeDocumentChunk.knowledge_document_id == document_id)
            .order_by(KnowledgeDocumentChunk.chunk_index)
            .all()
        )

    def delete_by_document_id(self, document_id: UUID) -> None:
        document_exists = (
            self.db.query(KnowledgeDocument.id)
            .filter(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.tenant_id == self.tenant_id,
            )
            .first()
        )
        if document_exists is None:
            raise ValueError(
                "The knowledge document does not belong to the current tenant."
            )

        (
            self.query()
            .filter(KnowledgeDocumentChunk.knowledge_document_id == document_id)
            .delete(synchronize_session=False)
        )

    def search_similar(
        self,
        embedding: list[float],
        limit: int,
        category: KnowledgeDocumentCategory | None = None,
        categories: set[KnowledgeDocumentCategory] | None = None,
    ) -> list[tuple[KnowledgeDocumentChunk, float]]:
        distance = KnowledgeDocumentChunk.embedding.cosine_distance(embedding).label(
            "distance"
        )
        query = (
            self.db.query(KnowledgeDocumentChunk, distance)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeDocumentChunk.knowledge_document_id,
            )
            .filter(
                KnowledgeDocumentChunk.tenant_id == self.tenant_id,
                KnowledgeDocument.tenant_id == self.tenant_id,
                KnowledgeDocument.status == KnowledgeDocumentStatus.ACTIVE,
            )
        )

        if category is not None and categories is not None:
            raise ValueError("Provide category or categories, not both.")
        if category is not None:
            query = query.filter(KnowledgeDocument.category == category.value)
        elif categories is not None:
            category_values = [item.value for item in categories]
            if not category_values:
                return []
            query = query.filter(KnowledgeDocument.category.in_(category_values))

        results = query.order_by(distance).limit(limit).all()
        return [(chunk, float(distance_value)) for chunk, distance_value in results]
