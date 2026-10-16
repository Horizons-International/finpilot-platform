from uuid import uuid4

from app.models.ai_model_metric import AIModelMetric
from app.models.ai_usage_log import AIUsageLog
from app.repositories.ai_usage_log_repository import AIUsageLogRepository
from app.utils.enums import UserRole
from tests.helpers import authenticate_client


def test_ai_usage_logs_update_metrics_endpoint(client, db_session, create_test_user):
    admin = create_test_user(
        email=f"ai-metrics-{uuid4()}@example.com", role=UserRole.ADMINISTRATOR
    )
    tenant_id = admin.tenant_id
    db_session.info["tenant_id"] = tenant_id
    model_name = f"metrics-test-{uuid4()}"
    repository = AIUsageLogRepository(db_session, tenant_id=tenant_id)

    repository.create(
        AIUsageLog(
            tenant_id=tenant_id,
            user_id=admin.id,
            feature="TEST_METRICS",
            model=model_name,
            input_tokens=10,
            output_tokens=5,
            response_time=40,
            error_message=None,
        )
    )
    repository.create(
        AIUsageLog(
            tenant_id=tenant_id,
            user_id=admin.id,
            feature="TEST_METRICS",
            model=model_name,
            input_tokens=0,
            output_tokens=0,
            response_time=80,
            error_message="simulated failure",
        )
    )
    db_session.commit()

    authenticate_client(client, admin)
    response = client.get("/api/v1/ai-model-metrics", params={"model_name": model_name})
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert len(rows) == 1
    assert rows[0]["request_count"] == 2
    assert rows[0]["success_count"] == 1
    assert rows[0]["error_count"] == 1
    assert rows[0]["average_response_time_ms"] == 60.0

    # The metric row is deliberately test-specific and removed to keep the
    # shared test database independent of this integration test.
    db_session.query(AIModelMetric).filter(
        AIModelMetric.tenant_id == tenant_id,
        AIModelMetric.model_name == model_name,
    ).delete(synchronize_session=False)
    db_session.query(AIUsageLog).filter(
        AIUsageLog.tenant_id == tenant_id,
        AIUsageLog.model == model_name,
        AIUsageLog.feature == "TEST_METRICS",
    ).delete(synchronize_session=False)
    db_session.commit()


def test_ai_model_metrics_are_tenant_scoped(client, db_session, create_test_user):
    user = create_test_user(
        email=f"ai-metrics-scope-{uuid4()}@example.com", role=UserRole.ADMINISTRATOR
    )
    authenticate_client(client, user)
    response = client.get("/api/v1/ai-model-metrics")
    assert response.status_code == 200, response.text
    assert isinstance(response.json()["data"], list)


def test_completed_interaction_feedback_updates_feedback_and_accuracy_metrics(
    client, db_session, create_test_user, cleanup_ai_prompts
):
    from app.models.ai_interaction import AIInteraction
    from app.models.ai_model_feedback import AIModelFeedback
    from app.models.ai_prompt import AIPrompt
    from app.utils.enums import AIFunction, AIInteractionStatus, AIResourceType
    from tests.seed import seed_ai_prompts

    user = create_test_user(
        email=f"ai-feedback-{uuid4()}@example.com", role=UserRole.ADMINISTRATOR
    )
    tenant_id = user.tenant_id
    db_session.info["tenant_id"] = tenant_id
    seed_ai_prompts(db_session)
    prompt = (
        db_session.query(AIPrompt)
        .filter(AIPrompt.tenant_id == tenant_id, AIPrompt.name == "case-summary")
        .first()
    )
    assert prompt is not None

    model_name = f"feedback-model-{uuid4()}"
    interaction = AIInteraction(
        tenant_id=tenant_id,
        user_id=user.id,
        ai_function=AIFunction.CASE_SUMMARY,
        prompt_id=prompt.id,
        resource_type=AIResourceType.CUSTOMER,
        resource_id=uuid4(),
        question="What does the policy require?",
        context={"knowledge_base": {"results": []}},
        response_data={"summary": "Test response"},
        response_text="Test response",
        model=model_name,
        status=AIInteractionStatus.COMPLETED,
    )
    db_session.add(interaction)
    db_session.commit()
    db_session.refresh(interaction)

    authenticate_client(client, user)
    response = client.post(
        f"/api/v1/ai-model-metrics/interactions/{interaction.id}/feedback",
        json={"rating": 5, "is_accurate": True, "comment": "Correct and useful."},
    )
    assert response.status_code == 201, response.text
    feedback_id = response.json()["data"]["id"]
    assert response.json()["data"]["rating"] == 5
    assert response.json()["data"]["is_accurate"] is True

    metrics = client.get("/api/v1/ai-model-metrics", params={"model_name": model_name})
    assert metrics.status_code == 200, metrics.text
    row = metrics.json()["data"][0]
    assert row["feedback_count"] == 1
    assert row["average_feedback_rating"] == 5.0
    assert row["positive_feedback_rate"] == 1.0
    assert row["accuracy_measurement_count"] == 1
    assert row["measured_accuracy_rate"] == 1.0

    db_session.query(AIModelFeedback).filter(
        AIModelFeedback.id == feedback_id,
        AIModelFeedback.tenant_id == tenant_id,
    ).delete(synchronize_session=False)
    db_session.query(AIInteraction).filter(
        AIInteraction.id == interaction.id,
        AIInteraction.tenant_id == tenant_id,
    ).delete(synchronize_session=False)
    db_session.query(AIModelMetric).filter(
        AIModelMetric.tenant_id == tenant_id,
        AIModelMetric.model_name == model_name,
    ).delete(synchronize_session=False)
    db_session.commit()
