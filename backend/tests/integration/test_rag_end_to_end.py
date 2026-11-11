from unittest.mock import patch

import pytest

from app.utils.enums import UserRole
from tests.helpers import authenticate_client


class FakeEmbeddingService:
    def embed_many(self, texts):
        return [[0.1] * 1536 for _ in texts]

    def embed_query(self, text):
        return [0.1] * 1536


@pytest.mark.anyio
async def test_complete_rag_pipeline(
    client,
    create_test_user,
    cleanup_ai_prompts,
    cleanup_ai_data,
    cleanup_test_customers,
    cleanup_knowledge_documents,
    cleanup_test_files,
):
    admin = create_test_user(
        email="rag-e2e-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    # 1. Upload knowledge document.
    upload_response = client.post(
        "/api/v1/knowledge-documents",
        files={
            "file": (
                "verification-policy.txt",
                (
                    b"Customer verification requires a "
                    b"valid government-issued identity "
                    b"document."
                ),
                "text/plain",
            )
        },
        data={
            "name": "Customer Verification Policy",
            "category": "COMPLIANCE_POLICY",
        },
    )

    assert upload_response.status_code == 201
    document = upload_response.json()["data"]
    document_id = document["id"]
    cleanup_test_files(document["file_reference"])

    # 2. Activate document.
    activate_response = client.patch(
        f"/api/v1/knowledge-documents/{document_id}/status",
        json={"status": "ACTIVE"},
    )
    assert activate_response.status_code == 200

    # 3. Index through the async API and async indexing service.
    with patch(
        "app.core.async_dependencies.EmbeddingService",
        return_value=FakeEmbeddingService(),
    ):
        indexing_response = client.post(
            f"/api/v1/knowledge-documents/{document_id}/index"
        )

    assert indexing_response.status_code == 200
    assert indexing_response.json()["data"]["document_id"] == document_id
    assert indexing_response.json()["data"]["chunks_indexed"] > 0

    # 4. Retrieve through the asynchronous RAG endpoint.
    with patch(
        "app.rag.async_retrieval.EmbeddingService",
        return_value=FakeEmbeddingService(),
    ):
        retrieval_response = client.post(
            "/api/v1/rag/retrieve",
            json={
                "query": "What identity document is required?",
                "limit": 5,
            },
        )

    assert retrieval_response.status_code == 200
    results = retrieval_response.json()["data"]
    assert results
    assert any(
        "government-issued" in result["content"] for result in results["results"]
    )

    # 5. Ask the existing synchronous AI assistant. Its service layer is
    # intentionally outside this migration step and continues using the
    # synchronous retriever until that service is migrated separately.
    customer_response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "John",
            "middle_name": "Michael",
            "last_name": "Smith",
            "date_of_birth": "1990-05-15",
            "nationality": "US",
            "country_of_residence": "US",
            "email": "rag-e2e-customer@example.com",
            "phone_number": "+249912345678",
            "status": "new",
        },
    )
    assert customer_response.status_code == 201
    customer_id = customer_response.json()["data"]["id"]

    with patch("app.core.dependencies.RetrievalService") as retrieval_service_class:
        fake_retrieval_service = retrieval_service_class.return_value
        fake_retrieval_service.search.return_value = results
        ai_response = client.post(
            "/api/v1/ai-assistant/ask",
            json={
                "ai_function": "CUSTOMER_SUMMARY",
                "question": "What identity document is required?",
                "customer_id": customer_id,
                "retrieval_limit": 5,
            },
        )

    assert ai_response.status_code == 201
    assert ai_response.json()["data"]["status"] == "COMPLETED"
