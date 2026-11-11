from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_chunk import KnowledgeDocumentChunk
from app.repositories.async_tenant_scoped_repository import (
    AsyncTenantScopedRepository,
    resolve_async_tenant_id,
)
from app.utils.enums import KnowledgeDocumentCategory, KnowledgeDocumentStatus


class AsyncKnowledgeDocumentChunkRepository(
    AsyncTenantScopedRepository[KnowledgeDocumentChunk]
):
    def __init__(self, db: AsyncSession, tenant_id: UUID | None = None) -> None:
        resolved_tenant_id = resolve_async_tenant_id(db, tenant_id)
        assert resolved_tenant_id is not None
        super().__init__(
            db=db,
            model=KnowledgeDocumentChunk,
            tenant_id=resolved_tenant_id,
        )

    async def _validate_document(self, chunk: KnowledgeDocumentChunk) -> None:
        document_id = await self.db.scalar(
            select(KnowledgeDocument.id).where(
                KnowledgeDocument.id == chunk.knowledge_document_id,
                KnowledgeDocument.tenant_id == self.tenant_id,
            )
        )
        if document_id is None:
            raise ValueError(
                "The knowledge document does not belong to the current tenant."
            )

    async def create(
        self,
        chunk: KnowledgeDocumentChunk,
    ) -> KnowledgeDocumentChunk:
        await self._validate_document(chunk)
        return await super().create(chunk)

    async def update(
        self,
        chunk: KnowledgeDocumentChunk,
    ) -> KnowledgeDocumentChunk:
        await self._validate_document(chunk)
        return await super().update(chunk)

    async def get_by_document_id(
        self,
        document_id: UUID,
    ) -> list[KnowledgeDocumentChunk]:
        statement = (
            self.query()
            .where(KnowledgeDocumentChunk.knowledge_document_id == document_id)
            .order_by(KnowledgeDocumentChunk.chunk_index)
        )
        result = await self.db.scalars(statement)
        return list(result.all())

    async def delete_by_document_id(self, document_id: UUID) -> None:
        document_exists = await self.db.scalar(
            select(KnowledgeDocument.id).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.tenant_id == self.tenant_id,
            )
        )
        if document_exists is None:
            raise ValueError(
                "The knowledge document does not belong to the current tenant."
            )

        statement = (
            delete(KnowledgeDocumentChunk)
            .where(
                KnowledgeDocumentChunk.tenant_id == self.tenant_id,
                KnowledgeDocumentChunk.knowledge_document_id == document_id,
            )
            .execution_options(synchronize_session=False)
        )
        await self.db.execute(statement)

    async def search_similar(
        self,
        embedding: list[float],
        limit: int,
        category: KnowledgeDocumentCategory | None = None,
        categories: set[KnowledgeDocumentCategory] | None = None,
    ) -> list[tuple[KnowledgeDocumentChunk, float]]:
        if category is not None and categories is not None:
            raise ValueError("Provide category or categories, not both.")

        distance = KnowledgeDocumentChunk.embedding.cosine_distance(embedding).label(
            "distance"
        )
        statement = (
            select(KnowledgeDocumentChunk, distance)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeDocumentChunk.knowledge_document_id,
            )
            .where(
                KnowledgeDocumentChunk.tenant_id == self.tenant_id,
                KnowledgeDocument.tenant_id == self.tenant_id,
                KnowledgeDocument.status == KnowledgeDocumentStatus.ACTIVE,
            )
        )

        if category is not None:
            statement = statement.where(KnowledgeDocument.category == category.value)
        elif categories is not None:
            category_values = [item.value for item in categories]
            if not category_values:
                return []
            statement = statement.where(KnowledgeDocument.category.in_(category_values))

        statement = statement.order_by(distance).limit(limit)
        result = await self.db.execute(statement)
        return [
            (chunk, float(distance_value)) for chunk, distance_value in result.all()
        ]
