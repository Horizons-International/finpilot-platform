"""Small atomic write helpers used by the central AI usage-log repository."""

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_model_metric import AIModelMetric


def metric_model_name(model: str | None) -> str:
    normalized = model.strip() if model else ""
    if normalized:
        return normalized[:200]
    provider = settings.AI_PROVIDER.strip() if settings.AI_PROVIDER else ""
    return (provider or "unknown")[:200]


def metric_model_version() -> str:
    configured = settings.AI_MODEL_VERSION.strip()
    return (configured or "unspecified")[:100]


def record_ai_model_request(
    db: Session,
    *,
    tenant_id: UUID,
    model: str | None,
    response_time_ms: int,
    error_message: str | None,
) -> None:
    """Atomically increment aggregate request, error/success and latency counts."""
    model_name = metric_model_name(model)
    model_version = metric_model_version()
    failed = error_message is not None
    statement = insert(AIModelMetric).values(
        tenant_id=tenant_id,
        model_name=model_name,
        model_version=model_version,
        request_count=1,
        success_count=0 if failed else 1,
        error_count=1 if failed else 0,
        total_response_time_ms=max(0, int(response_time_ms)),
        feedback_count=0,
        feedback_rating_sum=0,
        positive_feedback_count=0,
        accuracy_measurement_count=0,
        correct_prediction_count=0,
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_ai_model_metrics_tenant_model_version",
        set_={
            "request_count": AIModelMetric.request_count + 1,
            "success_count": AIModelMetric.success_count + (0 if failed else 1),
            "error_count": AIModelMetric.error_count + (1 if failed else 0),
            "total_response_time_ms": AIModelMetric.total_response_time_ms
            + max(0, int(response_time_ms)),
            "updated_at": func.now(),
        },
    )
    # The project's Session listener disallows bulk INSERTs into tenant-owned
    # tables by default. This atomic UPSERT is explicitly reviewed: its insert
    # values always include the trusted current tenant ID and its conflict key
    # includes that same tenant, so it cannot update another tenant's metric.
    db.execute(
        statement.execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason=(
                "atomic AI model metric upsert scoped by trusted tenant and model key"
            ),
        )
    )
