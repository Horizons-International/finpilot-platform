import pytest

from app.models.file import File
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_chunk import (
    KnowledgeDocumentChunk,
)
from app.services.file_service import FileService
from app.services.knowledge_indexing_service import (
    KnowledgeIndexingService,
)
from app.storages.local_storage import LocalStorage
from app.utils.enums import (
    KnowledgeDocumentCategory,
    KnowledgeDocumentStatus,
    UserRole,
)
from tests.helpers import authenticate_client


class FailingEmbeddingService:
    def embed_many(self, texts):
        raise RuntimeError("Embedding provider unavailable")


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


def create_knowledge_document(
    db_session,
    user_id,
    file_id,
    version: str,
    name: str = "AML Policy",
):
    document = KnowledgeDocument(
        name=name,
        category=KnowledgeDocumentCategory.COMPLIANCE_POLICY.value,
        file_reference=str(file_id),
        version=version,
        status=KnowledgeDocumentStatus.ACTIVE,
        uploaded_by=user_id,
    )

    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    return document


def test_new_document_version_starts_inactive(
    db_session,
    client,
    create_test_user,
    cleanup_test_files,
    cleanup_knowledge_documents,
    cleanup_ai_prompts,
    tmp_path,
):
    admin = create_test_user(
        email="rag-version-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    storage = LocalStorage(str(tmp_path))

    file_record = create_file(
        db_session=db_session,
        storage=storage,
        user_id=admin.id,
        filename="inactive.txt",
        content=b"Some compliance content.",
    )

    cleanup_test_files(file_record.id)

    document = create_knowledge_document(
        db_session,
        user_id=admin.id,
        file_id=file_record.id,
        version=1,
    )

    response = client.post(
        f"/api/v1/knowledge-documents/{document.id}/versions",
        files={
            "file": (
                "policy-v2.txt",
                b"Updated verification policy.",
                "text/plain",
            )
        },
        data={
            "category": "COMPLIANCE_POLICY",
        },
    )

    assert response.status_code in {
        200,
        201,
    }

    data = response.json()["data"]

    assert data["version"] == 2
    assert data["status"] == "INACTIVE"


def test_old_active_version_remains_active_until_explicitly_deactivated(
    db_session,
    client,
    create_test_user,
    cleanup_test_files,
    cleanup_knowledge_documents,
    tmp_path,
):
    admin = create_test_user(
        email="rag-version-active@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    storage = LocalStorage(str(tmp_path))

    file_record = create_file(
        db_session=db_session,
        storage=storage,
        user_id=admin.id,
        filename="inactive.txt",
        content=b"Some compliance content.",
    )

    cleanup_test_files(file_record.id)

    document = create_knowledge_document(
        db_session,
        user_id=admin.id,
        file_id=file_record.id,
        version=1,
    )

    response = client.post(
        f"/api/v1/knowledge-documents/{document.id}/versions",
        files={
            "file": (
                "policy-v2.txt",
                b"Updated policy.",
                "text/plain",
            )
        },
        data={
            "category": "COMPLIANCE_POLICY",
        },
    )

    assert response.status_code in {
        200,
        201,
    }

    old_document = client.get(
        f"/api/v1/knowledge-documents/{document.id}",
    )

    assert old_document.status_code == 200
    assert old_document.json()["data"]["status"] == "ACTIVE"


def test_only_one_active_version_is_allowed(
    db_session,
    client,
    create_test_user,
    cleanup_test_files,
    cleanup_knowledge_documents,
    tmp_path,
):
    admin = create_test_user(
        email="rag-version-unique@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    storage = LocalStorage(str(tmp_path))

    file_record = create_file(
        db_session=db_session,
        storage=storage,
        user_id=admin.id,
        filename="inactive.txt",
        content=b"Some compliance content.",
    )

    cleanup_test_files(file_record.id)

    document = create_knowledge_document(
        db_session,
        user_id=admin.id,
        file_id=file_record.id,
        version=1,
    )

    response = client.post(
        f"/api/v1/knowledge-documents/{document.id}/versions",
        files={
            "file": (
                "policy-v2.txt",
                b"Updated policy.",
                "text/plain",
            )
        },
        data={
            "category": "COMPLIANCE_POLICY",
        },
    )

    assert response.status_code in {
        200,
        201,
    }

    version_id = response.json()["data"]["id"]

    activate_response = client.patch(
        f"/api/v1/knowledge-documents/{version_id}/status",
        json={
            "status": "ACTIVE",
        },
    )

    assert activate_response.status_code == 400


@pytest.mark.anyio
async def test_embedding_failure_rolls_back_chunks(
    db_session,
    client,
    create_test_user,
    cleanup_test_files,
    cleanup_knowledge_documents,
    tmp_path,
):
    admin = create_test_user(
        email="rag-rollback@example.com", role=UserRole.ADMINISTRATOR
    )

    authenticate_client(client, admin)

    storage = LocalStorage(str(tmp_path))

    file_record = create_file(
        db_session=db_session,
        storage=storage,
        user_id=admin.id,
        filename="inactive.txt",
        content=b"Some compliance content.",
    )

    cleanup_test_files(file_record.id)

    file_service = FileService(
        db=db_session,
        storage=storage,
    )

    document = create_knowledge_document(
        db_session,
        user_id=admin.id,
        file_id=file_record.id,
        version=1,
    )

    service = KnowledgeIndexingService(
        db=db_session,
        file_service=file_service,
        embedding_service=FailingEmbeddingService(),
    )

    with pytest.raises(RuntimeError):
        await service.index_document(
            document_id=document.id,
            user_id=admin.id,
            email=admin.email,
        )

    chunks = (
        db_session.query(KnowledgeDocumentChunk)
        .filter(KnowledgeDocumentChunk.knowledge_document_id == document.id)
        .all()
    )

    assert chunks == []


@pytest.mark.anyio
async def test_failed_reindex_does_not_leave_partial_chunks(
    db_session,
    client,
    create_test_user,
    cleanup_test_files,
    cleanup_knowledge_documents,
    tmp_path,
):
    admin = create_test_user(
        email="rag-reindex-rollback@example.com", role=UserRole.ADMINISTRATOR
    )

    authenticate_client(client, admin)

    storage = LocalStorage(str(tmp_path))

    file_record = create_file(
        db_session=db_session,
        storage=storage,
        user_id=admin.id,
        filename="inactive.txt",
        content=b"Some compliance content.",
    )

    cleanup_test_files(file_record.id)

    file_service = FileService(
        db=db_session,
        storage=storage,
    )

    document = create_knowledge_document(
        db_session,
        user_id=admin.id,
        file_id=file_record.id,
        version=1,
    )

    class WorkingEmbeddingService:
        def embed_many(self, texts):
            return [[0.1] * 1536 for _ in texts]

    service = KnowledgeIndexingService(
        db=db_session,
        file_service=file_service,
        embedding_service=WorkingEmbeddingService(),
    )

    await service.index_document(
        document_id=document.id,
        user_id=admin.id,
        email=admin.email,
    )

    original_chunks = (
        db_session.query(KnowledgeDocumentChunk)
        .filter(KnowledgeDocumentChunk.knowledge_document_id == document.id)
        .all()
    )

    assert original_chunks

    class FailingEmbeddingService:
        def embed_many(self, texts):
            raise RuntimeError("embedding failure")

    service = KnowledgeIndexingService(
        db_session,
        file_service=file_service,
        embedding_service=FailingEmbeddingService(),
    )

    with pytest.raises(RuntimeError):
        await service.index_document(
            document_id=document.id,
            user_id=admin.id,
            email=admin.email,
        )

    remaining_chunks = (
        db_session.query(KnowledgeDocumentChunk)
        .filter(KnowledgeDocumentChunk.knowledge_document_id == document.id)
        .all()
    )

    # The transaction must have been rolled back.
    assert len(remaining_chunks) == len(original_chunks)
