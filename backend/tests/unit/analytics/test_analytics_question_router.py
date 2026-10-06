from datetime import timedelta

import pytest

from app.analytics.assistant.question_router import (
    resolve_analytics_question,
)
from app.schemas.ai_analytics_assistant import (
    AnalyticsQuestionType,
)
from app.utils.date_time import utc_now


def test_resolves_pending_verification_this_month():
    plan = resolve_analytics_question(
        "How many customers are pending verification this month?",
    )

    today = utc_now().date()
    current_month_start = today.replace(day=1)

    assert plan.question_type == AnalyticsQuestionType.PENDING_VERIFICATION
    assert plan.start_date == current_month_start
    assert plan.end_date == today
    assert plan.comparison_end_date == (current_month_start - timedelta(days=1))


def test_resolves_sla_metric():
    plan = resolve_analytics_question(
        "What is the SLA compliance this month?",
    )

    assert plan.question_type == AnalyticsQuestionType.CONFIGURED_METRIC
    assert plan.metric_key == "sla_compliance_percentage"


def test_resolves_verification_rejection_reason():
    plan = resolve_analytics_question(
        "What is the main reason for rejected verification?",
    )

    assert plan.question_type == AnalyticsQuestionType.VERIFICATION_REJECTION_REASONS


def test_resolves_last_30_days():
    plan = resolve_analytics_question(
        "How many tasks were completed in the last 30 days?",
    )

    assert plan.question_type == AnalyticsQuestionType.TASK_PERFORMANCE


def test_rejects_unsupported_question():
    with pytest.raises(Exception):
        resolve_analytics_question(
            "Tell me about the weather.",
        )
