from app.rag.context import RAGContextBuilder
from app.utils.enums import KnowledgeDocumentCategory
from tests.helpers import (
    FakeRetrievalService,
    create_fake_retrieval_result,
)


def test_build_rag_context():
    result = create_fake_retrieval_result()

    retrieval_service = FakeRetrievalService(
        results=[result],
    )

    builder = RAGContextBuilder(
        retrieval_service=retrieval_service,
    )

    context = builder.build(
        query="What identity document is required?",
        limit=5,
    )

    assert context["query"] == ("What identity document is required?")

    assert len(context["results"]) == 1

    retrieved = context["results"][0]

    assert retrieved["chunk_id"] == str(result.chunk_id)

    assert retrieved["document_id"] == str(result.document_id)

    assert retrieved["document_name"] == ("Customer Verification Policy")

    assert retrieved["category"] == ("COMPLIANCE_POLICY")

    assert retrieved["version"] == 1

    assert retrieved["content"] == (
        "Customers must provide a valid identity document for verification."
    )

    assert retrieved["similarity"] == 0.92


def test_build_rag_context_passes_category():
    retrieval_service = FakeRetrievalService()

    builder = RAGContextBuilder(
        retrieval_service=retrieval_service,
    )

    category = KnowledgeDocumentCategory.COMPLIANCE_POLICY

    builder.build(
        query="verification requirements",
        category=category,
        limit=3,
    )

    assert retrieval_service.last_query == ("verification requirements")

    assert retrieval_service.last_limit == 3

    assert retrieval_service.last_category == category


def test_build_without_retrieval_service_returns_empty_context():
    builder = RAGContextBuilder()

    context = builder.build(
        query="What is the policy?",
    )

    assert context == {
        "query": "What is the policy?",
        "results": [],
    }
