"""Async knowledge indexing, with blocking extraction/embedding offloaded."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_chunk import KnowledgeDocumentChunk
from app.rag.chunking import chunk_text
from app.rag.embeddings import EmbeddingService
from app.rag.extraction import extract_text
from app.repositories.async_knowledge_document_chunk_repository import (
    AsyncKnowledgeDocumentChunkRepository,
)
from app.repositories.async_knowledge_document_repository import (
    AsyncKnowledgeDocumentRepository,
)
from app.services.async_file_service import AsyncFileService, bind_async_tenant
from app.utils.enums import KnowledgeDocumentStatus
from app.utils.errors import bad_request, not_found


class AsyncKnowledgeIndexingService:
    def __init__(
        self,
        db: AsyncSession,
        file_service: AsyncFileService,
        embedding_service: EmbeddingService,
        tenant_id: UUID,
    ) -> None:
        if file_service.db is not db or file_service.tenant_id != tenant_id:
            raise ValueError(
                "Knowledge indexing and file services must share the same "
                "AsyncSession and tenant."
            )
        bind_async_tenant(db, tenant_id)
        self.db = db
        self.tenant_id = tenant_id
        self.file_service = file_service
        self.embedding_service = embedding_service
        self.knowledge_document_repository = AsyncKnowledgeDocumentRepository(
            db=db,
            tenant_id=tenant_id,
        )
        self.chunk_repository = AsyncKnowledgeDocumentChunkRepository(
            db,
            tenant_id,
        )

    async def index_document(
        self,
        document_id: UUID,
        user_id: UUID,
        email: str,
    ) -> list[KnowledgeDocumentChunk]:
        document = await self.knowledge_document_repository.get_by_id(document_id)
        if document is None:
            raise not_found("Knowledge document")
        if document.status != KnowledgeDocumentStatus.ACTIVE:
            raise bad_request("Only active knowledge documents can be indexed.")

        file_id = self._get_file_id(document)
        content, filename, content_type = await self.file_service.read_file(file_id)

        extracted_text = await run_in_threadpool(
            extract_text,
            content=content,
            filename=filename,
            content_type=content_type,
        )
        chunks = await run_in_threadpool(chunk_text, extracted_text)
        if not chunks:
            raise bad_request("The knowledge document produced no text chunks.")

        embeddings = await run_in_threadpool(
            self.embedding_service.embed_many,
            [chunk.content for chunk in chunks],
        )

        try:
            await self.chunk_repository.delete_by_document_id(document_id)
            records: list[KnowledgeDocumentChunk] = []
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                record = KnowledgeDocumentChunk(
                    tenant_id=self.tenant_id,
                    knowledge_document_id=document_id,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    embedding=embedding,
                )
                await self.chunk_repository.create(record)
                records.append(record)

            await self.db.commit()
            return records
        except Exception:
            await self.db.rollback()
            raise

    @staticmethod
    def _get_file_id(document: KnowledgeDocument) -> UUID:
        try:
            return UUID(document.file_reference)
        except ValueError as exc:
            raise bad_request(
                "Knowledge document has an invalid file reference."
            ) from exc
