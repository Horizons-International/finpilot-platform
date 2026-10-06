import re
from datetime import date, timedelta

from app.schemas.ai_analytics_assistant import (
    AnalyticsQuestionPlan,
    AnalyticsQuestionType,
)
from app.utils.date_time import utc_now
from app.utils.errors import bad_request

METRIC_ALIASES = (
    (
        "verification completion rate",
        "verification_completion_rate",
    ),
    (
        "verification completion percentage",
        "verification_completion_rate",
    ),
    (
        "verification approval rate",
        "verification_approval_rate",
    ),
    (
        "verification approval percentage",
        "verification_approval_rate",
    ),
    (
        "customer registration rate",
        "customer_registration_rate",
    ),
    (
        "registration rate",
        "customer_registration_rate",
    ),
    (
        "average compliance review time",
        "average_compliance_review_time",
    ),
    (
        "alert resolution time",
        "alert_resolution_time",
    ),
    (
        "high risk customer percentage",
        "high_risk_customer_percentage",
    ),
    (
        "high-risk customer percentage",
        "high_risk_customer_percentage",
    ),
    (
        "task completion rate",
        "task_completion_rate",
    ),
    (
        "sla compliance percentage",
        "sla_compliance_percentage",
    ),
    (
        "sla compliance",
        "sla_compliance_percentage",
    ),
)


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _previous_month_end(value: date) -> date:
    return _month_start(value) - timedelta(days=1)


def _previous_period(
    start_date: date,
    end_date: date,
) -> tuple[date, date]:
    period_length = (end_date - start_date).days + 1

    comparison_end = start_date - timedelta(days=1)

    comparison_start = comparison_end - timedelta(
        days=period_length - 1,
    )

    return comparison_start, comparison_end


def _resolve_dates(
    question: str,
    today: date,
) -> tuple[date, date, date, date]:
    normalized_question = question.lower()

    # Today.
    if "today" in normalized_question:
        start_date = today
        end_date = today

        comparison_start, comparison_end = _previous_period(
            start_date,
            end_date,
        )

        return (
            start_date,
            end_date,
            comparison_start,
            comparison_end,
        )

    # Current calendar month.
    if "this month" in normalized_question or "current month" in normalized_question:
        start_date = _month_start(today)
        end_date = today

        comparison_end = _previous_month_end(today)
        comparison_start = _month_start(comparison_end)

        return (
            start_date,
            end_date,
            comparison_start,
            comparison_end,
        )

    # Previous calendar month.
    if "last month" in normalized_question or "previous month" in normalized_question:
        end_date = _previous_month_end(today)
        start_date = _month_start(end_date)

        previous_month_end = _previous_month_end(start_date)
        comparison_start = _month_start(previous_month_end)
        comparison_end = previous_month_end

        return (
            start_date,
            end_date,
            comparison_start,
            comparison_end,
        )

    # Current week, Monday through today.
    if "this week" in normalized_question:
        start_date = today - timedelta(
            days=today.weekday(),
        )
        end_date = today

        comparison_start, comparison_end = _previous_period(
            start_date,
            end_date,
        )

        return (
            start_date,
            end_date,
            comparison_start,
            comparison_end,
        )

    # Previous full week.
    if "last week" in normalized_question or "previous week" in normalized_question:
        current_week_start = today - timedelta(
            days=today.weekday(),
        )

        end_date = current_week_start - timedelta(days=1)
        start_date = end_date - timedelta(days=6)

        comparison_start, comparison_end = _previous_period(
            start_date,
            end_date,
        )

        return (
            start_date,
            end_date,
            comparison_start,
            comparison_end,
        )

    # Rolling N-day period.
    match = re.search(
        r"(?:last|past)\s+(\d{1,3})\s+days?",
        normalized_question,
    )

    if match:
        days = int(match.group(1))

        if days < 1 or days > 366:
            raise bad_request(
                "Analytics question date ranges must be between 1 and 366 days.",
            )

        start_date = today - timedelta(
            days=days - 1,
        )
        end_date = today

        comparison_start, comparison_end = _previous_period(
            start_date,
            end_date,
        )

        return (
            start_date,
            end_date,
            comparison_start,
            comparison_end,
        )

    # Default: last 30 calendar days.
    end_date = today
    start_date = today - timedelta(days=29)

    comparison_start, comparison_end = _previous_period(
        start_date,
        end_date,
    )

    return (
        start_date,
        end_date,
        comparison_start,
        comparison_end,
    )


def _resolve_question_type(
    question: str,
) -> tuple[AnalyticsQuestionType, str | None]:
    normalized_question = " ".join(
        question.lower().split(),
    )

    # Configurable metrics first.
    # Longest phrases come before shorter aliases.
    for phrase, metric_key in sorted(
        METRIC_ALIASES,
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if phrase in normalized_question:
            return (
                AnalyticsQuestionType.CONFIGURED_METRIC,
                metric_key,
            )

    if "pending verification" in normalized_question or (
        "pending" in normalized_question and "verification" in normalized_question
    ):
        return (
            AnalyticsQuestionType.PENDING_VERIFICATION,
            None,
        )

    if (
        "rejected verification" in normalized_question
        or (
            "rejection" in normalized_question and "verification" in normalized_question
        )
        or ("reject" in normalized_question and "verification" in normalized_question)
    ):
        return (
            AnalyticsQuestionType.VERIFICATION_REJECTION_REASONS,
            None,
        )

    if (
        "registration" in normalized_question
        or "registered customers" in normalized_question
        or "new customers" in normalized_question
    ):
        return (
            AnalyticsQuestionType.CUSTOMER_REGISTRATIONS,
            None,
        )

    if "aml" in normalized_question or "alert" in normalized_question:
        return (
            AnalyticsQuestionType.AML_ALERTS,
            None,
        )

    if "risk" in normalized_question:
        return (
            AnalyticsQuestionType.RISK_DISTRIBUTION,
            None,
        )

    if (
        "compliance case" in normalized_question
        or "compliance cases" in normalized_question
    ):
        return (
            AnalyticsQuestionType.COMPLIANCE_CASES,
            None,
        )

    if "task" in normalized_question:
        return (
            AnalyticsQuestionType.TASK_PERFORMANCE,
            None,
        )

    if "workflow" in normalized_question:
        return (
            AnalyticsQuestionType.WORKFLOW_PERFORMANCE,
            None,
        )

    raise bad_request(
        "I could not identify a supported analytics question. "
        "Try asking about customers, verification, risk, AML alerts, "
        "compliance cases, tasks, workflows, or a configured metric.",
    )


def resolve_analytics_question(
    question: str,
) -> AnalyticsQuestionPlan:
    normalized_question = " ".join(
        question.strip().split(),
    )

    if not normalized_question:
        raise bad_request(
            "Analytics question is required.",
        )

    question_type, metric_key = _resolve_question_type(
        normalized_question,
    )

    (
        start_date,
        end_date,
        comparison_start_date,
        comparison_end_date,
    ) = _resolve_dates(
        normalized_question,
        utc_now().date(),
    )

    return AnalyticsQuestionPlan(
        question_type=question_type,
        metric_key=metric_key,
        start_date=start_date,
        end_date=end_date,
        comparison_start_date=comparison_start_date,
        comparison_end_date=comparison_end_date,
    )
