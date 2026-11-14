"""Native-async AI usage metering and model metrics."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_model_metric import AIModelMetric
from app.models.ai_usage_log import AIUsageLog
from app.models.user import User
from app.services.ai_model_metric_recorder import (
    metric_model_name,
    metric_model_version,
)
from app.services.async_subscription_service import record_subscription_usage


class AsyncAIUsageService:
    """Record AI usage and model metrics after subscription quota metering.

    Subscription metering uses the established async subscription service, which
    commits its own usage-counter transaction. The AI usage log and aggregate
    model metric are then staged in the caller's transaction.
    """

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant_id = db.info.get("tenant_id")
        if active_tenant_id is not None and active_tenant_id != tenant_id:
            raise ValueError(
                "AI usage tenant does not match the active session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    async def record(
        self,
        *,
        user_id: UUID,
        feature: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        response_time: int,
        error_message: str | None = None,
        commit: bool = False,
        meter_subscription: bool = True,
    ) -> AIUsageLog:
        user_exists = await self.db.scalar(
            select(User.id).where(
                User.id == user_id,
                User.tenant_id == self.tenant_id,
            )
        )
        if user_exists is None:
            raise ValueError("The AI usage log user does not belong to this tenant.")

        if meter_subscription:
            await record_subscription_usage(self.db, self.tenant_id, "ai_requests")
        usage_log = AIUsageLog(
            tenant_id=self.tenant_id,
            user_id=user_id,
            feature=feature,
            model=model[:100],
            input_tokens=max(0, input_tokens),
            output_tokens=max(0, output_tokens),
            response_time=max(0, response_time),
            error_message=error_message,
        )
        self.db.add(usage_log)

        model_name = metric_model_name(model)
        model_version = metric_model_version()
        failed = error_message is not None
        statement = insert(AIModelMetric).values(
            tenant_id=self.tenant_id,
            model_name=model_name,
            model_version=model_version,
            request_count=1,
            success_count=0 if failed else 1,
            error_count=1 if failed else 0,
            total_response_time_ms=max(0, response_time),
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
                + max(0, response_time),
                "updated_at": func.now(),
            },
        )
        await self.db.execute(
            statement.execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "atomic AI model metric upsert scoped by trusted tenant "
                    "and model key"
                ),
            )
        )
        await self.db.flush()
        if commit:
            await self.db.commit()
            await self.db.refresh(usage_log)
        return usage_log
