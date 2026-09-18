# fmt: off

import io
from uuid import UUID

import pytest
from fastapi import HTTPException, UploadFile

from app.models.audit_log import AuditLog
from app.models.file import File
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_chunk import KnowledgeDocumentChunk
from app.services.file_service import FileService
from app.services.knowledge_indexing_service import KnowledgeIndexingService
from app.storages.local_storage import LocalStorage
from app.utils.enums import (
    AuditEventType,
    KnowledgeDocumentCategory,
    KnowledgeDocumentStatus,
)


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_many(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        self.calls.append(texts)

        embeddings: list[list[float]] = []

        for index, _text in enumerate(texts):
            value = float(index + 1)

            embeddings.append([value] * 1536)

        return embeddings


class FakeStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def save(
        self,
        file_content: bytes,
        filename: str,
        folder: str,
    ) -> str:
        path = f"{folder}/{filename}"

        self.files[path] = file_content

        return path

    def read(self, storage_path: str) -> bytes:
        return self.files[storage_path]

    def delete(self, storage_path: str) -> None:
        del self.files[storage_path]

    def exists(self, storage_path: str) -> bool:
        return storage_path in self.files


def create_file(
    db_session,
    storage,
    user_id,
    filename: str,
    content: bytes,
):
    storage_path = storage.save(
        file_content=content,
        filename=filename,
        folder="knowledge-base/documents",
    )

    file_record = File(
        original_filename=filename,
        stored_filename=filename,
        storage_path=storage_path,
        folder="documents",
        module="knowledge-base",
        content_type="text/plain",
        file_size=len(content),
        uploaded_by=user_id,
    )

    db_session.add(file_record)
    db_session.commit()
    db_session.refresh(file_record)

    return file_record


async def awaitable_index(
    indexing_service,
    document_id,
    user_id,
    email,
):
    return await indexing_service.index_document(
        document_id=document_id,
        user_id=user_id,
        email=email,
    )


@pytest.mark.anyio
async def test_index_active_knowledge_document(
    db_session,
    create_test_user,
    cleanup_test_files,
    cleanup_knowledge_documents,
):
    user = create_test_user(
        email="rag-indexing@example.com",
        role="Administrator",
    )

    storage = FakeStorage()

    file_service = FileService(
        db=db_session,
        storage=storage,
    )

    upload = UploadFile(
        file=io.BytesIO(b"""
            Anti-money laundering policy requires customer
            identity verification before account activation.

            High-risk customers must undergo enhanced due diligence.

            Suspicious transactions must be reported according
            to the applicable regulatory procedure.
            """),
        filename="aml-policy.txt",
        headers={"content-type": "text/plain"},
    )

    file_record = await file_service.upload_file(
        file=upload,
        uploaded_by=user.id,
        email=user.email,
        module="knowledge-base",
        folder="documents",
    )

    cleanup_test_files(file_record.id)

    document = KnowledgeDocument(
        name="AML Policy",
        category=KnowledgeDocumentCategory.COMPLIANCE_POLICY.value,
        file_reference=str(file_record.id),
        version=1,
        status=KnowledgeDocumentStatus.ACTIVE,
        uploaded_by=user.id,
    )

    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    embedding_service = FakeEmbeddingService()

    indexing_service = KnowledgeIndexingService(
        db=db_session,
        file_service=file_service,
        embedding_service=embedding_service,
    )

    chunks = await indexing_service.index_document(
        document_id=document.id,
        user_id=user.id,
        email=user.email,
    )

    assert chunks

    stored_chunks = (
        db_session.query(KnowledgeDocumentChunk)
        .filter(KnowledgeDocumentChunk.knowledge_document_id == document.id)
        .order_by(KnowledgeDocumentChunk.chunk_index)
        .all()
    )

    assert len(stored_chunks) == len(chunks)

    assert all(chunk.knowledge_document_id == document.id for chunk in stored_chunks)

    assert [chunk.chunk_index for chunk in stored_chunks] == list(
        range(len(stored_chunks))
    )

    assert all(chunk.content for chunk in stored_chunks)

    assert all(len(chunk.embedding) == 1536 for chunk in stored_chunks)

    assert embedding_service.calls

    assert embedding_service.calls[0] == [chunk.content for chunk in chunks]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status",
    [
        KnowledgeDocumentStatus.INACTIVE,
    ],
)
async def test_inactive_document_cannot_be_indexed(
    db_session,
    create_test_user,
    cleanup_test_files,
    cleanup_knowledge_documents,
    tmp_path,
    status,
):
    user = create_test_user(
        email="rag-inactive@example.com",
        role="Administrator",
    )

    storage = LocalStorage(str(tmp_path))

    file_record = create_file(
        db_session=db_session,
        storage=storage,
        user_id=user.id,
        filename="inactive.txt",
        content=b"Some compliance content.",
    )

    cleanup_test_files(file_record.id)

    document = KnowledgeDocument(
        name="Inactive Policy",
        category=KnowledgeDocumentCategory.COMPLIANCE_POLICY.value,
        file_reference=str(file_record.id),
        version=1,
        status=status,
        uploaded_by=user.id,
    )

    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    embedding_service = FakeEmbeddingService()

    file_service = FileService(
        db=db_session,
        storage=storage,
    )

    indexing_service = KnowledgeIndexingService(
        db=db_session,
        file_service=file_service,
        embedding_service=embedding_service,
    )

    with pytest.raises(HTTPException) as exc_info:
        await indexing_service.index_document(
            document_id=document.id,
            user_id=user.id,
            email=user.email,
        )

    assert "Only active knowledge documents can be indexed" in str(exc_info.value)
    assert exc_info.value.status_code == 400

    assert embedding_service.calls == []


@pytest.mark.anyio
async def test_indexing_missing_document_returns_404(
    db_session,
    create_test_user,
    tmp_path,
):
    user = create_test_user(
        email="rag-not-found@example.com",
        role="Administrator",
    )

    storage = LocalStorage(str(tmp_path))

    embedding_service = FakeEmbeddingService()

    file_service = FileService(
        db=db_session,
        storage=storage,
    )

    indexing_service = KnowledgeIndexingService(
        db=db_session,
        file_service=file_service,
        embedding_service=embedding_service,
    )

    with pytest.raises(HTTPException) as exc_info:
        await indexing_service.index_document(
            document_id=UUID("00000000-0000-0000-0000-000000000000"),
            user_id=user.id,
            email=user.email,
        )

    assert "Knowledge document" in str(exc_info.value)
    assert exc_info.value.status_code == 404


@pytest.mark.anyio
async def test_indexing_invalid_file_reference_returns_400(
    db_session,
    create_test_user,
    cleanup_knowledge_documents,
    tmp_path,
):
    user = create_test_user(
        email="rag-invalid-file-reference@example.com",
        role="Administrator",
    )

    document = KnowledgeDocument(
        name="Invalid File Reference Policy",
        category=KnowledgeDocumentCategory.COMPLIANCE_POLICY.value,
        file_reference="not-a-uuid",
        version=1,
        status=KnowledgeDocumentStatus.ACTIVE,
        uploaded_by=user.id,
    )

    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    storage = LocalStorage(str(tmp_path))

    indexing_service = KnowledgeIndexingService(
        db=db_session,
        file_service=FileService(
            db=db_session,
            storage=storage,
        ),
        embedding_service=FakeEmbeddingService(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await indexing_service.index_document(
            document_id=document.id,
            user_id=user.id,
            email=user.email,
        )

    assert "invalid file reference" in str(exc_info.value).lower()
    assert exc_info.value.status_code == 400


@pytest.mark.anyio
async def test_indexing_does_not_create_file_download_audit(
    db_session,
    create_test_user,
    cleanup_test_files,
    cleanup_knowledge_documents,
):
    user = create_test_user(
        email="rag-no-download-audit@example.com",
        role="Administrator",
    )

    storage = FakeStorage()

    file_service = FileService(
        db=db_session,
        storage=storage,
    )

    upload = UploadFile(
        file=io.BytesIO(b"Compliance policy content for indexing."),
        filename="policy.txt",
        headers={"content-type": "text/plain"},
    )

    file_record = await file_service.upload_file(
        file=upload,
        uploaded_by=user.id,
        email=user.email,
        module="knowledge-base",
        folder="documents",
    )

    cleanup_test_files(file_record.id)

    document = KnowledgeDocument(
        name="Audit Test Policy",
        category=KnowledgeDocumentCategory.COMPLIANCE_POLICY.value,
        file_reference=str(file_record.id),
        version=1,
        status=KnowledgeDocumentStatus.ACTIVE,
        uploaded_by=user.id,
    )

    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    indexing_service = KnowledgeIndexingService(
        db=db_session,
        file_service=file_service,
        embedding_service=FakeEmbeddingService(),
    )

    await indexing_service.index_document(
        document_id=document.id,
        user_id=user.id,
        email=user.email,
    )

    download_audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == user.id,
            AuditLog.event_type == AuditEventType.FILE_DOWNLOAD,
            AuditLog.resource_id == file_record.id,
        )
        .first()
    )

    assert download_audit is None
