from uuid import uuid4

from app.services.ai_context_service import AIContextService
from app.utils.enums import (
    AIFunction,
    AIResourceType,
)
from tests.helpers import (
    FakeRetrievalService,
    create_fake_retrieval_result,
)


def test_ai_context_includes_rag_results(
    db_session,
    monkeypatch,
):
    customer_id = uuid4()

    retrieval_result = create_fake_retrieval_result()

    retrieval_service = FakeRetrievalService(
        results=[retrieval_result],
    )

    service = AIContextService(
        db_session,
        retrieval_service=retrieval_service,
    )

    def fake_platform_context(
        ai_function,
        *,
        customer_id=None,
        verification_case_id=None,
        document_id=None,
    ):
        return (
            {
                "customer": {
                    "id": str(customer_id),
                },
            },
            AIResourceType.CUSTOMER,
            customer_id,
        )

    monkeypatch.setattr(
        service.compliance_context_service,
        "build_context",
        fake_platform_context,
    )

    context, resource_type, resource_id = service.build_context(
        AIFunction.CUSTOMER_SUMMARY,
        question="What verification policy applies?",
        customer_id=customer_id,
    )

    assert context["customer"]["id"] == str(customer_id)

    assert "knowledge_base" in context

    knowledge_base = context["knowledge_base"]

    assert knowledge_base["query"] == ("What verification policy applies?")

    assert len(knowledge_base["results"]) == 1

    assert resource_id == customer_id
