import pytest

from app.models.ai_usage_log import AIUsageLog
from app.utils.enums import UserRole
from tests.helpers import authenticate_client


def create_usage_log(
    db_session,
    *,
    user_id,
    feature="CASE_SUMMARY",
    model="mock",
    input_tokens=100,
    output_tokens=50,
    response_time=500,
    error_message=None,
):
    usage_log = AIUsageLog(
        user_id=user_id,
        feature=feature,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        response_time=response_time,
        error_message=error_message,
    )

    db_session.add(usage_log)
    db_session.commit()
    db_session.refresh(usage_log)

    return usage_log


def test_administrator_can_query_ai_usage(
    client,
    create_test_user,
    cleanup_ai_data,
    db_session,
):
    admin = create_test_user(
        email="usage-query-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    create_usage_log(
        db_session,
        user_id=admin.id,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.get(
        "/api/v1/ai-usage",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["total"] >= 1
    assert len(data["items"]) >= 1

    item = data["items"][0]

    assert item["user_id"] == str(admin.id)
    assert item["feature"] == "CASE_SUMMARY"
    assert item["model"] == "mock"
    assert item["input_tokens"] == 100
    assert item["output_tokens"] == 50
    assert item["response_time"] == 500
    assert item["error_message"] is None


def test_administrator_can_filter_usage_by_feature(
    client,
    create_test_user,
    cleanup_ai_data,
    db_session,
):
    admin = create_test_user(
        email="usage-filter-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    create_usage_log(
        db_session,
        user_id=admin.id,
        feature="CASE_SUMMARY",
    )

    create_usage_log(
        db_session,
        user_id=admin.id,
        feature="CUSTOMER_SUMMARY",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.get(
        "/api/v1/ai-usage",
        params={
            "feature": "CASE_SUMMARY",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["feature"] == "CASE_SUMMARY"


def test_administrator_can_filter_usage_by_user(
    client,
    create_test_user,
    cleanup_ai_data,
    db_session,
):
    admin = create_test_user(
        email="usage-filter-user-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    other_user = create_test_user(
        email="usage-filter-other@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    create_usage_log(
        db_session,
        user_id=admin.id,
    )

    create_usage_log(
        db_session,
        user_id=other_user.id,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.get(
        "/api/v1/ai-usage",
        params={
            "user_id": str(other_user.id),
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["user_id"] == str(other_user.id)


def test_administrator_can_query_ai_usage_summary(
    client,
    create_test_user,
    cleanup_ai_data,
    db_session,
):
    admin = create_test_user(
        email="usage-summary-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    create_usage_log(
        db_session,
        user_id=admin.id,
        input_tokens=100,
        output_tokens=50,
        response_time=400,
    )

    create_usage_log(
        db_session,
        user_id=admin.id,
        input_tokens=200,
        output_tokens=100,
        response_time=600,
    )

    create_usage_log(
        db_session,
        user_id=admin.id,
        input_tokens=50,
        output_tokens=25,
        response_time=1000,
        error_message="Provider failed.",
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.get(
        "/api/v1/ai-usage/summary",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["total_requests"] == 3
    assert data["total_errors"] == 1
    assert data["successful_requests"] == 2

    assert data["total_input_tokens"] == 350
    assert data["total_output_tokens"] == 175

    assert data["average_response_time"] == pytest.approx(
        666.6666666666666,
    )


def test_compliance_officer_cannot_query_ai_usage(
    client,
    create_test_user,
    cleanup_ai_data,
):
    user = create_test_user(
        email="usage-officer@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(
        client,
        user,
    )

    response = client.get(
        "/api/v1/ai-usage",
    )

    assert response.status_code == 403


def test_reviewer_cannot_query_ai_usage(
    client,
    create_test_user,
):
    user = create_test_user(
        email="usage-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        user,
    )

    response = client.get(
        "/api/v1/ai-usage",
    )

    assert response.status_code == 403


def test_auditor_cannot_query_ai_usage(
    client,
    create_test_user,
):
    user = create_test_user(
        email="usage-auditor@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(
        client,
        user,
    )

    response = client.get(
        "/api/v1/ai-usage",
    )

    assert response.status_code == 403


def test_non_administrator_cannot_query_ai_usage_summary(
    client,
    create_test_user,
):
    user = create_test_user(
        email="usage-summary-officer@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(
        client,
        user,
    )

    response = client.get(
        "/api/v1/ai-usage/summary",
    )

    assert response.status_code == 403
