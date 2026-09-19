from app.services.ai_usage_service import AIUsageService
from app.utils.enums import UserRole


def test_record_creates_usage_log(
    create_test_user,
    cleanup_ai_data,
    db_session,
):
    admin = create_test_user(
        email="usage_create@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    service = AIUsageService(db_session)

    usage_log = service.record(
        user_id=admin.id,
        feature="CASE_SUMMARY",
        model="mock-model",
        input_tokens=120,
        output_tokens=80,
        response_time=350,
    )

    assert usage_log.id is not None
    assert usage_log.user_id == admin.id
    assert usage_log.feature == "CASE_SUMMARY"
    assert usage_log.model == "mock-model"
    assert usage_log.input_tokens == 120
    assert usage_log.output_tokens == 80
    assert usage_log.response_time == 350
    assert usage_log.error_message is None
    assert usage_log.created_at is not None


def test_record_creates_failed_usage_log(
    create_test_user,
    cleanup_ai_data,
    db_session,
):
    admin = create_test_user(
        email="usage_create@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    service = AIUsageService(db_session)

    usage_log = service.record(
        user_id=admin.id,
        feature="CASE_SUMMARY",
        model="mock-model",
        input_tokens=0,
        output_tokens=0,
        response_time=125,
        error_message="AI provider failed.",
    )

    assert usage_log.id is not None
    assert usage_log.user_id == admin.id
    assert usage_log.feature == "CASE_SUMMARY"
    assert usage_log.model == "mock-model"
    assert usage_log.input_tokens == 0
    assert usage_log.output_tokens == 0
    assert usage_log.response_time == 125
    assert usage_log.error_message == "AI provider failed."


def test_record_can_defer_commit(
    create_test_user,
    cleanup_ai_data,
    db_session,
):
    admin = create_test_user(
        email="usage_create@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    service = AIUsageService(db_session)

    usage_log = service.record(
        user_id=admin.id,
        feature="CUSTOMER_SUMMARY",
        model="mock-model",
        input_tokens=10,
        output_tokens=20,
        response_time=50,
        commit=False,
    )

    assert usage_log.id is not None
    assert usage_log.user_id == admin.id
    assert usage_log.feature == "CUSTOMER_SUMMARY"
