from unittest.mock import patch
from uuid import UUID, uuid4

from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_chunk import (
    KnowledgeDocumentChunk,
)
from app.rag.retrieval import RetrievalService
from app.utils.enums import (
    KnowledgeDocumentCategory,
    KnowledgeDocumentStatus,
    UserRole,
)
from tests.helpers import authenticate_client


def create_document(
    db_session,
    *,
    id: UUID,
    name: str,
    category: KnowledgeDocumentCategory,
    status: KnowledgeDocumentStatus,
) -> KnowledgeDocument:
    document = KnowledgeDocument(
        id=uuid4(),
        name=name,
        category=category.value,
        file_reference=str(uuid4()),
        version=1,
        status=status,
        uploaded_by=id,
    )

    db_session.add(document)
    db_session.flush()

    return document


def create_chunk(
    db_session,
    *,
    document: KnowledgeDocument,
    index: int,
    content: str,
    embedding: list[float],
) -> KnowledgeDocumentChunk:
    chunk = KnowledgeDocumentChunk(
        id=uuid4(),
        knowledge_document_id=document.id,
        chunk_index=index,
        content=content,
        embedding=embedding,
    )

    db_session.add(chunk)
    db_session.flush()

    return chunk


def test_vector_search_returns_closest_active_chunk(
    db_session,
    create_test_user,
    cleanup_knowledge_documents,
):
    admin = create_test_user(email="rag1@example.com", role=UserRole.ADMINISTRATOR)

    document = create_document(
        db_session,
        id=admin.id,
        name="Customer Verification Policy",
        category=KnowledgeDocumentCategory.COMPLIANCE_POLICY,
        status=KnowledgeDocumentStatus.ACTIVE,
    )

    close_chunk = create_chunk(
        db_session,
        document=document,
        index=0,
        content=(
            "Customers must provide a valid identity document before verification."
        ),
        embedding=[1.0] + [0.0] * 1535,
    )

    far_chunk = create_chunk(
        db_session,
        document=document,
        index=1,
        content=("The organization maintains records for financial reporting."),
        embedding=[0.0] + [1.0] + [0.0] * 1534,
    )

    db_session.commit()

    embed = type(
        "FakeEmbeddingService",
        (),
        {"embed_query": lambda self, query: ([1.0] + [0.0] * 1535)},
    )()

    service = RetrievalService(
        db_session,
        embedding_service=embed,
    )

    results = service.retrieve(
        query="What identity document is required?",
        limit=2,
    )

    assert len(results) == 2

    assert results[0].chunk_id == close_chunk.id
    assert results[0].content == (
        "Customers must provide a valid identity document before verification."
    )

    assert results[0].similarity > results[1].similarity
    assert results[0].similarity == 1.0

    assert far_chunk.id == results[1].chunk_id


def test_vector_search_excludes_inactive_documents(
    db_session,
    create_test_user,
    cleanup_knowledge_documents,
):
    admin = create_test_user(email="rag1@example.com", role=UserRole.ADMINISTRATOR)

    active_document = create_document(
        db_session,
        id=admin.id,
        name="Active Policy",
        category=KnowledgeDocumentCategory.COMPLIANCE_POLICY,
        status=KnowledgeDocumentStatus.ACTIVE,
    )

    inactive_document = create_document(
        db_session,
        id=admin.id,
        name="Inactive Policy",
        category=KnowledgeDocumentCategory.COMPLIANCE_POLICY,
        status=KnowledgeDocumentStatus.INACTIVE,
    )

    active_chunk = create_chunk(
        db_session,
        document=active_document,
        index=0,
        content="Active policy content.",
        embedding=[1.0] + [0.0] * 1535,
    )

    create_chunk(
        db_session,
        document=inactive_document,
        index=0,
        content="Inactive policy content.",
        embedding=[1.0] + [0.0] * 1535,
    )

    db_session.commit()

    embed = type(
        "FakeEmbeddingService",
        (),
        {"embed_query": lambda self, query: ([1.0] + [0.0] * 1535)},
    )()

    service = RetrievalService(
        db_session,
        embedding_service=embed,
    )

    results = service.retrieve(
        query="policy",
        limit=10,
    )

    assert len(results) == 1

    assert results[0].chunk_id == active_chunk.id
    assert results[0].document_name == "Active Policy"


def test_vector_search_filters_by_category(
    db_session,
    create_test_user,
    cleanup_knowledge_documents,
):
    admin = create_test_user(email="rag1@example.com", role=UserRole.ADMINISTRATOR)

    compliance_document = create_document(
        db_session,
        id=admin.id,
        name="Compliance Policy",
        category=KnowledgeDocumentCategory.COMPLIANCE_POLICY,
        status=KnowledgeDocumentStatus.ACTIVE,
    )

    product_document = create_document(
        db_session,
        id=admin.id,
        name="Product Documentation",
        category=KnowledgeDocumentCategory.PRODUCT_DOCUMENTATION,
        status=KnowledgeDocumentStatus.ACTIVE,
    )

    compliance_chunk = create_chunk(
        db_session,
        document=compliance_document,
        index=0,
        content="Compliance policy information.",
        embedding=[1.0] + [0.0] * 1535,
    )

    create_chunk(
        db_session,
        document=product_document,
        index=0,
        content="Product documentation information.",
        embedding=[1.0] + [0.0] * 1535,
    )

    db_session.commit()

    embed = type(
        "FakeEmbeddingService",
        (),
        {"embed_query": lambda self, query: ([1.0] + [0.0] * 1535)},
    )()

    service = RetrievalService(
        db_session,
        embedding_service=embed,
    )

    results = service.retrieve(
        query="information",
        limit=10,
        category=(KnowledgeDocumentCategory.COMPLIANCE_POLICY),
    )

    assert len(results) == 1

    assert results[0].chunk_id == compliance_chunk.id
    assert results[0].category == KnowledgeDocumentCategory.COMPLIANCE_POLICY


def test_retrieve_knowledge_endpoint(
    client,
    create_test_user,
):
    user = create_test_user(email="rag-user@example.com", role=UserRole.ADMINISTRATOR)

    authenticate_client(client, user)

    with patch("app.rag.retrieval.EmbeddingService") as embedding_service_class:
        embedding_service = embedding_service_class.return_value

        embedding_service.embed_query.return_value = [0.1] * 1536

        response = client.post(
            "/api/v1/rag/retrieve",
            json={
                "query": "What is customer verification?",
                "limit": 5,
            },
        )

    assert response.status_code == 200

    data = response.json()

    assert data["success"] is True
    assert "data" in data
    assert "results" in data["data"]
