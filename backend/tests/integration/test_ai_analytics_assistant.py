from datetime import date
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.ai.schemas.responses import AIResponse
from app.analytics.models.customer_daily import (
    CustomerAnalyticsDaily,
)
from app.models.ai_interaction import AIInteraction
from app.models.verification_case import (
    IdentityVerificationCase,
)
from app.models.verification_review import (
    VerificationReview,
)
from app.utils.enums import (
    AIFunction,
    AIResourceType,
    ReviewDecision,
    UserRole,
    VerificationStatus,
    VerificationType,
)
from tests.conftest import TestSessionLocal
from tests.helpers import (
    FakeRetrievalService,
    authenticate_client,
    create_customer_with_data,
    create_fake_retrieval_result,
)
from tests.seed import seed_ai_prompts


@pytest.fixture(autouse=True)
def seed_ai_assistant_data():
    seed_analytics_ai_data()


def seed_analytics_ai_data():
    db = TestSessionLocal()

    try:
        seed_ai_prompts(db)
    finally:
        db.close()


def make_customer_snapshot(
    db_session,
    *,
    snapshot_date: date,
    pending_verification: int,
) -> CustomerAnalyticsDaily:
    snapshot = CustomerAnalyticsDaily(
        snapshot_date=snapshot_date,
        ending_total_customers=100,
        customers_registered_during_day=10,
        verification_approvals_during_day=5,
        ending_pending_verification_customers=pending_verification,
        ending_verified_customers=70,
        ending_suspended_customers=5,
        ending_rejected_customers=5,
    )

    db_session.add(snapshot)
    db_session.commit()
    db_session.refresh(snapshot)

    return snapshot


def test_ai_analytics_assistant_answers_pending_verification(
    client,
    create_test_user,
    cleanup_ai_data,
    cleanup_analytics_snapshots,
    db_session,
):
    admin = create_test_user(
        email="analytics-ai-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    today = date.today()

    current_month_start = today.replace(day=1)

    previous_month_end = current_month_start - __import__("datetime").timedelta(days=1)

    make_customer_snapshot(
        db_session,
        snapshot_date=previous_month_end,
        pending_verification=200,
    )

    make_customer_snapshot(
        db_session,
        snapshot_date=today,
        pending_verification=224,
    )

    fake_retrieval_service = FakeRetrievalService(
        results=[],
    )

    fake_ai_response = AIResponse(
        provider_name="mock",
        request_type="analytics_assistant",
        content="Analytics answer generated.",
        structured_data={
            "summary": (
                "There are 224 customers pending verification, "
                "up 12% from the previous comparison period."
            ),
            "suggested_insights": [
                "Pending verification volume increased by 12%.",
            ],
            "confidence": 0.98,
        },
        request_id=uuid4(),
        input_tokens=100,
        output_tokens=30,
    )

    with (
        patch(
            "app.core.dependencies.RetrievalService",
            return_value=fake_retrieval_service,
        ),
        patch(
            "app.services.ai_analytics_assistant_service.AIService.generate",
            return_value=fake_ai_response,
        ),
    ):
        response = client.post(
            "/api/v1/ai-assistant/analytics/ask",
            params={
                "question": ("How many customers are pending verification this month?"),
            },
        )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["ai_function"] == AIFunction.ANALYTICS_ASSISTANT.value

    assert data["result"]["summary"].startswith(
        "There are 224 customers",
    )

    supporting_data = data["result"]["supporting_data"]

    assert len(supporting_data) == 1

    evidence = supporting_data[0]

    assert evidence["key"] == "pending_verification_customers"
    assert evidence["value"] == 224
    assert evidence["comparison_value"] == 200
    assert evidence["comparison_change_percentage"] == 12.0


def test_ai_analytics_interaction_stores_supporting_data(
    client,
    create_test_user,
    cleanup_ai_data,
    cleanup_analytics_snapshots,
    db_session,
):
    admin = create_test_user(
        email="analytics-ai-storage@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    today = date.today()

    make_customer_snapshot(
        db_session,
        snapshot_date=today,
        pending_verification=245,
    )

    fake_ai_response = AIResponse(
        provider_name="mock",
        request_type="analytics_assistant",
        content="Analytics answer generated.",
        structured_data={
            "summary": "245 customers are pending verification.",
            "suggested_insights": [],
            "confidence": 0.95,
        },
        request_id=uuid4(),
        input_tokens=20,
        output_tokens=10,
    )

    with patch(
        "app.services.ai_analytics_assistant_service.AIService.generate",
        return_value=fake_ai_response,
    ):
        response = client.post(
            "/api/v1/ai-assistant/analytics/ask",
            params={
                "question": ("How many customers are pending verification today?"),
            },
        )

    assert response.status_code == 201

    interaction_id = response.json()["data"]["interaction_id"]

    interaction = db_session.get(
        AIInteraction,
        interaction_id,
    )

    assert interaction is not None

    assert interaction.ai_function == (AIFunction.ANALYTICS_ASSISTANT)

    assert interaction.resource_type == (AIResourceType.ANALYTICS)

    assert interaction.response_data is not None

    assert interaction.response_data["supporting_data"][0]["value"] == 245


def test_ai_analytics_assistant_answers_rejection_reason(
    client,
    create_test_user,
    cleanup_ai_data,
    cleanup_test_customers,
    db_session,
):
    admin = create_test_user(
        email="analytics-rejection@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="analytics-rejection-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    response = create_customer_with_data(
        client,
        country_of_residence="Sudan",
    )

    assert response.status_code == 201

    customer_id = response.json()["data"]["id"]

    verification_case = IdentityVerificationCase(
        customer_id=customer_id,
        verification_type=VerificationType.IDENTITY,
        status=VerificationStatus.REJECTED,
    )

    db_session.add(verification_case)
    db_session.flush()

    db_session.add(
        VerificationReview(
            verification_case_id=verification_case.id,
            reviewer_id=reviewer.id,
            decision=ReviewDecision.REJECT,
            notes="Missing documents",
        )
    )

    db_session.commit()

    authenticate_client(
        client,
        admin,
    )

    fake_ai_response = AIResponse(
        provider_name="mock",
        request_type="analytics_assistant",
        content="Analytics answer generated.",
        structured_data={
            "summary": ("Missing documents is the main rejection reason."),
            "suggested_insights": [
                "Document completeness appears to be the main verification bottleneck."
            ],
            "confidence": 0.96,
        },
        request_id=uuid4(),
        input_tokens=20,
        output_tokens=15,
    )

    with patch(
        "app.services.ai_analytics_assistant_service.AIService.generate",
        return_value=fake_ai_response,
    ):
        response = client.post(
            "/api/v1/ai-assistant/analytics/ask",
            params={
                "question": ("What is the main reason for rejected verification?"),
            },
        )

    assert response.status_code == 201

    data = response.json()["data"]

    evidence = data["result"]["supporting_data"][0]

    assert evidence["key"] == ("top_verification_rejection_reason")

    assert evidence["value"] == "Missing documents"
    assert evidence["details"]["count"] == 1


def test_reviewer_cannot_use_analytics_ai_assistant(
    client,
    create_test_user,
):
    reviewer = create_test_user(
        email="analytics-ai-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        reviewer,
    )

    response = client.post(
        "/api/v1/ai-assistant/analytics/ask",
        params={
            "question": ("How many customers are pending verification this month?"),
        },
    )

    assert response.status_code == 403


def test_ai_analytics_assistant_includes_rag_context(
    client,
    create_test_user,
    cleanup_ai_data,
    cleanup_analytics_snapshots,
    db_session,
):
    admin = create_test_user(
        email="analytics-rag@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    today = date.today()

    make_customer_snapshot(
        db_session,
        snapshot_date=today,
        pending_verification=245,
    )

    fake_retrieval_service = FakeRetrievalService(
        results=[
            create_fake_retrieval_result(),
        ],
    )

    fake_ai_response = AIResponse(
        provider_name="mock",
        request_type="analytics_assistant",
        content="Analytics answer generated.",
        structured_data={
            "summary": "245 customers are pending verification.",
            "suggested_insights": [
                "Review verification backlog capacity.",
            ],
            "confidence": 0.94,
        },
        request_id=uuid4(),
        input_tokens=50,
        output_tokens=20,
    )

    with (
        patch(
            "app.core.dependencies.RetrievalService",
            return_value=fake_retrieval_service,
        ),
        patch(
            "app.services.ai_analytics_assistant_service.AIService.generate",
            return_value=fake_ai_response,
        ),
    ):
        response = client.post(
            "/api/v1/ai-assistant/analytics/ask",
            params={
                "question": ("How many customers are pending verification today?"),
            },
        )

    assert response.status_code == 201
