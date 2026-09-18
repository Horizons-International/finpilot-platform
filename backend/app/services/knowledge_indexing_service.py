from uuid import UUID

from sqlalchemy.orm import Session

from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_chunk import KnowledgeDocumentChunk
from app.rag.chunking import chunk_text
from app.rag.embeddings import EmbeddingService
from app.rag.extraction import extract_text
from app.repositories.knowledge_document_chunk_repository import (
    KnowledgeDocumentChunkRepository,
)
from app.repositories.knowledge_document_repository import (
    KnowledgeDocumentRepository,
)
from app.services.file_service import FileService
from app.utils.enums import KnowledgeDocumentStatus
from app.utils.errors import bad_request, not_found


class KnowledgeIndexingService:
    def __init__(
        self,
        db: Session,
        file_service: FileService,
        embedding_service: EmbeddingService,
    ) -> None:
        self.db = db
        self.file_service = file_service
        self.embedding_service = embedding_service

        self.knowledge_document_repository = KnowledgeDocumentRepository(db)

        self.chunk_repository = KnowledgeDocumentChunkRepository(db)

    async def index_document(
        self,
        document_id: UUID,
        user_id: UUID,
        email: str,
    ) -> list[KnowledgeDocumentChunk]:
        document = self.knowledge_document_repository.get_by_id(document_id)

        if document is None:
            raise not_found("Knowledge document")

        if document.status != KnowledgeDocumentStatus.ACTIVE:
            raise bad_request("Only active knowledge documents can be indexed.")

        file_id = self._get_file_id(document)

        content, filename, content_type = self.file_service.read_file(
            file_id=file_id,
        )

        text = extract_text(
            content=content,
            filename=filename,
            content_type=content_type,
        )

        chunks = chunk_text(text)

        if not chunks:
            raise bad_request("The knowledge document produced no text chunks.")

        embeddings = self.embedding_service.embed_many(
            [chunk.content for chunk in chunks]
        )

        try:
            self.chunk_repository.delete_by_document_id(document_id)

            records: list[KnowledgeDocumentChunk] = []

            for chunk, embedding in zip(
                chunks,
                embeddings,
                strict=True,
            ):
                record = KnowledgeDocumentChunk(
                    knowledge_document_id=document_id,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    embedding=embedding,
                )

                self.chunk_repository.create(record)
                records.append(record)

            self.db.commit()

            for record in records:
                self.db.refresh(record)

            return records

        except Exception:
            self.db.rollback()
            raise

    @staticmethod
    def _get_file_id(
        document: KnowledgeDocument,
    ) -> UUID:
        try:
            return UUID(document.file_reference)
        except ValueError as exc:
            raise bad_request(
                "Knowledge document has an invalid file reference."
            ) from exc
