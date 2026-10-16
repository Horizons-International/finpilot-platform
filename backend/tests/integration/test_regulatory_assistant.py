from unittest.mock import patch

from app.schemas.rag import RetrievalResult
from app.utils.enums import KnowledgeDocumentCategory, UserRole
from tests.helpers import authenticate_client, create_fake_retrieval_result


class FakeRegulatoryRetrievalService:
    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results
        self.last_query: str | None = None
        self.last_limit: int | None = None
        self.last_category: KnowledgeDocumentCategory | None = None
        self.last_categories: set[KnowledgeDocumentCategory] | None = None

    def retrieve(
        self,
        query: str,
        limit: int = 5,
        category: KnowledgeDocumentCategory | None = None,
        categories: set[KnowledgeDocumentCategory] | None = None,
    ) -> list[RetrievalResult]:
        self.last_query = query
        self.last_limit = limit
        self.last_category = category
        self.last_categories = categories

        results = self.results
        if category is not None:
            results = [item for item in results if item.category == category]
        elif categories is not None:
            results = [item for item in results if item.category in categories]
        return results[:limit]


def test_regulatory_question_returns_grounded_sources(
    client,
    create_test_user,
    cleanup_ai_data,
):
    officer = create_test_user(
        email="regulatory-assistant-officer@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )
    authenticate_client(client, officer)

    evidence = create_fake_retrieval_result(
        content=(
            "Customers must provide a valid government-issued identity document "
            "before identity verification can be completed."
        ),
        similarity=0.94,
    )
    fake_retrieval = FakeRegulatoryRetrievalService([evidence])
    with patch(
        "app.core.dependencies.RetrievalService",
        return_value=fake_retrieval,
    ):
        response = client.post(
            "/api/v1/ai-assistant/regulatory/ask",
            json={
                "question": "What document is required for customer verification?",
                "retrieval_limit": 5,
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["question"] == "What document is required for customer verification?"
    assert data["source_count"] == 1
    assert data["sources"][0]["reference"] == "S1"
    assert data["sources"][0]["title"] == "Customer Verification Policy"
    assert data["sources"][0]["category"] == "COMPLIANCE_POLICY"
    assert "government-issued identity document" in data["sources"][0]["excerpt"]
    assert "[S1]" in data["answer"]
    assert fake_retrieval.last_categories == {
        KnowledgeDocumentCategory.COMPLIANCE_POLICY,
        KnowledgeDocumentCategory.INTERNAL_PROCEDURE,
        KnowledgeDocumentCategory.REGULATORY_GUIDELINE,
    }


def test_regulatory_search_returns_sources_without_generating_answer(
    client,
    create_test_user,
):
    officer = create_test_user(
        email="regulatory-search-officer@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )
    authenticate_client(client, officer)
    evidence = create_fake_retrieval_result()
    fake_retrieval = FakeRegulatoryRetrievalService([evidence])

    with patch(
        "app.core.dependencies.RetrievalService",
        return_value=fake_retrieval,
    ):
        response = client.post(
            "/api/v1/ai-assistant/regulatory/search",
            json={
                "question": "Find the customer verification policy.",
                "category": "COMPLIANCE_POLICY",
                "retrieval_limit": 3,
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["query"] == "Find the customer verification policy."
    assert data["result_count"] == 1
    assert data["sources"][0]["reference"] == "S1"
    assert fake_retrieval.last_category == KnowledgeDocumentCategory.COMPLIANCE_POLICY
    assert fake_retrieval.last_limit == 3


def test_regulatory_assistant_abstains_when_no_sources_are_found(
    client,
    create_test_user,
    cleanup_ai_data,
):
    officer = create_test_user(
        email="regulatory-empty-officer@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )
    authenticate_client(client, officer)
    fake_retrieval = FakeRegulatoryRetrievalService([])

    with (
        patch(
            "app.core.dependencies.RetrievalService",
            return_value=fake_retrieval,
        ),
        patch(
            "app.services.regulatory_assistant_service.AIService.generate",
            side_effect=AssertionError("AI must not answer without evidence."),
        ),
    ):
        response = client.post(
            "/api/v1/ai-assistant/regulatory/ask",
            json={"question": "What is the mandatory retention period?"},
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["sources"] == []
    assert data["source_count"] == 0
    assert data["confidence"] == 0.0
    assert "could not find a relevant active" in data["answer"].lower()


def test_regulatory_assistant_rejects_product_document_category(
    client,
    create_test_user,
):
    officer = create_test_user(
        email="regulatory-category-officer@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )
    authenticate_client(client, officer)

    response = client.post(
        "/api/v1/ai-assistant/regulatory/search",
        json={
            "question": "Search product manual.",
            "category": "PRODUCT_DOCUMENTATION",
        },
    )

    assert response.status_code == 422
