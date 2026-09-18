from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_chunk import (
    KnowledgeDocumentChunk,
)
from app.rag.retrieval import (
    DEFAULT_RETRIEVAL_LIMIT,
    MAX_RETRIEVAL_LIMIT,
    RetrievalService,
)
from app.utils.enums import (
    KnowledgeDocumentCategory,
    KnowledgeDocumentStatus,
)


def create_chunk(
    *,
    document_name: str = "Customer Verification Policy",
    category: str = "COMPLIANCE_POLICY",
    version: int = 1,
) -> KnowledgeDocumentChunk:
    document = KnowledgeDocument(
        id=uuid4(),
        name=document_name,
        category=category,
        file_reference=str(uuid4()),
        version=version,
        status=KnowledgeDocumentStatus.ACTIVE,
        uploaded_by=uuid4(),
    )

    chunk = KnowledgeDocumentChunk(
        id=uuid4(),
        knowledge_document_id=document.id,
        chunk_index=0,
        content=(
            "Customers must provide valid identification "
            "documents before verification can be completed."
        ),
        embedding=[0.1] * 1536,
    )

    chunk.knowledge_document = document

    return chunk


def create_service():
    repository = MagicMock()
    embedding_service = MagicMock()

    service = object.__new__(RetrievalService)

    service.repository = repository
    service.embedding_service = embedding_service

    return service, repository, embedding_service


def test_retrieve_returns_relevant_results():
    service, repository, embedding_service = create_service()

    query_embedding = [0.2] * 1536

    embedding_service.embed_query.return_value = query_embedding

    chunk = create_chunk()

    repository.search_similar.return_value = [
        (chunk, 0.1),
    ]

    results = service.retrieve(
        query="What documents are required?",
        limit=5,
    )

    assert len(results) == 1

    result = results[0]

    assert result.chunk_id == chunk.id
    assert result.document_id == chunk.knowledge_document_id
    assert result.document_name == "Customer Verification Policy"
    assert result.category == KnowledgeDocumentCategory.COMPLIANCE_POLICY
    assert result.version == 1
    assert result.content.startswith("Customers must provide")
    assert result.similarity == pytest.approx(0.9)

    embedding_service.embed_query.assert_called_once_with(
        "What documents are required?"
    )

    repository.search_similar.assert_called_once_with(
        embedding=query_embedding,
        limit=5,
        category=None,
    )


def test_retrieve_strips_query_whitespace():
    service, repository, embedding_service = create_service()

    embedding_service.embed_query.return_value = [0.2] * 1536

    repository.search_similar.return_value = []

    service.retrieve(
        query="   customer verification   ",
    )

    embedding_service.embed_query.assert_called_once_with("customer verification")

    repository.search_similar.assert_called_once_with(
        embedding=[0.2] * 1536,
        limit=DEFAULT_RETRIEVAL_LIMIT,
        category=None,
    )


def test_retrieve_rejects_empty_query():
    service, _, _ = create_service()

    with pytest.raises(
        HTTPException,
        match="Retrieval query is required.",
    ) as exc_info:
        service.retrieve(query="")

    assert exc_info.value.status_code == 400


def test_retrieve_rejects_zero_limit():
    service, _, _ = create_service()

    with pytest.raises(
        HTTPException,
        match="Retrieval limit must be greater than zero.",
    ) as exc_info:
        service.retrieve(
            query="customer verification",
            limit=0,
        )

    assert exc_info.value.status_code == 400


def test_retrieve_rejects_limit_above_maximum():
    service, _, _ = create_service()

    with pytest.raises(
        HTTPException,
        match=(f"Retrieval limit cannot exceed {MAX_RETRIEVAL_LIMIT}."),
    ) as exc_info:
        service.retrieve(
            query="customer verification",
            limit=MAX_RETRIEVAL_LIMIT + 1,
        )

    assert exc_info.value.status_code == 400


def test_retrieve_passes_category_filter():
    service, repository, embedding_service = create_service()

    embedding_service.embed_query.return_value = [0.2] * 1536

    repository.search_similar.return_value = []

    category = KnowledgeDocumentCategory.COMPLIANCE_POLICY

    service.retrieve(
        query="customer verification",
        limit=3,
        category=category,
    )

    repository.search_similar.assert_called_once_with(
        embedding=[0.2] * 1536,
        limit=3,
        category=category,
    )


def test_similarity_is_calculated_from_cosine_distance():
    service, repository, embedding_service = create_service()

    embedding_service.embed_query.return_value = [0.2] * 1536

    chunk = create_chunk()

    repository.search_similar.return_value = [
        (chunk, 0.25),
    ]

    results = service.retrieve(
        query="verification requirements",
    )

    assert results[0].similarity == pytest.approx(0.75)
