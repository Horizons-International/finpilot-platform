from unittest.mock import patch

import pytest

from app.services.file_service import FileService
from app.services.knowledge_indexing_service import (
    KnowledgeIndexingService,
)
from app.storages.local_storage import LocalStorage
from app.utils.enums import UserRole
from tests.helpers import authenticate_client


class FakeEmbeddingService:
    def embed_many(self, texts):
        return [[0.1] * 1536 for _ in texts]

    def embed_query(self, text):
        return [0.1] * 1536


@pytest.mark.anyio
async def test_complete_rag_pipeline(
    db_session,
    client,
    create_test_user,
    cleanup_ai_prompts,
    cleanup_ai_data,
    cleanup_test_customers,
    cleanup_knowledge_documents,
    cleanup_test_files,
    tmp_path,
):
    admin = create_test_user(
        email="rag-e2e-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    # ---------------------------------------------------------
    # 1. Upload knowledge document
    # ---------------------------------------------------------

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

    cleanup_test_files(upload_response.json()["data"]["file_reference"])

    assert upload_response.status_code == 201

    document = upload_response.json()["data"]

    document_id = document["id"]

    # ---------------------------------------------------------
    # 2. Activate document
    # ---------------------------------------------------------

    activate_response = client.patch(
        f"/api/v1/knowledge-documents/{document_id}/status",
        json={
            "status": "ACTIVE",
        },
    )

    assert activate_response.status_code == 200

    # ---------------------------------------------------------
    # 3. Index document
    # ---------------------------------------------------------

    storage = LocalStorage(str(tmp_path))

    file_service = FileService(
        db=db_session,
        storage=storage,
    )

    indexing_service = KnowledgeIndexingService(
        db=db_session,
        file_service=file_service,
        embedding_service=FakeEmbeddingService(),
    )

    await indexing_service.index_document(
        document_id,
        user_id=admin.id,
        email=admin.email,
    )

    # ---------------------------------------------------------
    # 4. Retrieve through RAG
    # ---------------------------------------------------------

    with patch(
        "app.rag.retrieval.EmbeddingService",
        return_value=FakeEmbeddingService(),
    ):
        retrieval_response = client.post(
            "/api/v1/rag/retrieve",
            json={
                "query": ("What identity document is required?"),
                "limit": 5,
            },
        )

    assert retrieval_response.status_code == 200

    results = retrieval_response.json()["data"]

    assert results

    assert any(
        "government-issued" in result["content"] for result in results["results"]
    )

    # ---------------------------------------------------------
    # 5. Ask AI assistant
    # ---------------------------------------------------------

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

    with patch(
        "app.services.ai_compliance_dependencies.RetrievalService",
    ) as retrieval_service_class:
        fake_retrieval_service = retrieval_service_class.return_value

        fake_retrieval_service.search.return_value = results

        ai_response = client.post(
            "/api/v1/ai-assistant/ask",
            json={
                "ai_function": "CUSTOMER_SUMMARY",
                "question": ("What identity document is required?"),
                "customer_id": customer_id,
                "retrieval_limit": 5,
            },
        )

    assert ai_response.status_code == 200

    data = ai_response.json()["data"]

    assert data["status"] == "COMPLETED"
