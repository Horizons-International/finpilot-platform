"""Async AI model performance reads and feedback writes."""

from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_interaction import AIInteraction
from app.models.ai_model_feedback import AIModelFeedback
from app.models.ai_model_metric import AIModelMetric
from app.schemas.ai_model_metrics import (
    AIModelMetricResponse,
    AIModelMetricsSummaryResponse,
)
from app.services.ai_model_metric_recorder import (
    metric_model_name,
    metric_model_version,
)
from app.utils.enums import AIInteractionStatus
from app.utils.errors import conflict, not_found


class AsyncAIModelMetricsService:
    """Tenant-scoped AI performance metrics with atomic aggregate feedback updates."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant_id = db.info.get("tenant_id")
        if active_tenant_id is not None and active_tenant_id != tenant_id:
            raise ValueError(
                "AI metrics tenant does not match the active session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    @staticmethod
    def _response(metric: AIModelMetric) -> AIModelMetricResponse:
        requests = int(metric.request_count)
        feedback_count = int(metric.feedback_count)
        accuracy_count = int(metric.accuracy_measurement_count)
        return AIModelMetricResponse(
            id=metric.id,
            model_name=metric.model_name,
            model_version=metric.model_version,
            request_count=requests,
            success_count=int(metric.success_count),
            error_count=int(metric.error_count),
            average_response_time_ms=(
                float(metric.total_response_time_ms) / requests if requests else 0.0
            ),
            feedback_count=feedback_count,
            average_feedback_rating=(
                float(metric.feedback_rating_sum) / feedback_count
                if feedback_count
                else None
            ),
            positive_feedback_rate=(
                float(metric.positive_feedback_count) / feedback_count
                if feedback_count
                else None
            ),
            accuracy_measurement_count=accuracy_count,
            measured_accuracy_rate=(
                float(metric.correct_prediction_count) / accuracy_count
                if accuracy_count
                else None
            ),
            created_at=metric.created_at,
            updated_at=metric.updated_at,
        )

    async def list_metrics(
        self, *, model_name: str | None = None, model_version: str | None = None
    ) -> list[AIModelMetricResponse]:
        statement = select(AIModelMetric).where(
            AIModelMetric.tenant_id == self.tenant_id
        )
        if model_name:
            statement = statement.where(AIModelMetric.model_name == model_name)
        if model_version:
            statement = statement.where(AIModelMetric.model_version == model_version)
        result = await self.db.scalars(
            statement.order_by(AIModelMetric.updated_at.desc())
        )
        return [self._response(metric) for metric in result.all()]

    async def get_summary(self) -> AIModelMetricsSummaryResponse:
        row = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(AIModelMetric.request_count), 0),
                    func.coalesce(func.sum(AIModelMetric.success_count), 0),
                    func.coalesce(func.sum(AIModelMetric.error_count), 0),
                    func.coalesce(func.sum(AIModelMetric.total_response_time_ms), 0),
                    func.coalesce(func.sum(AIModelMetric.feedback_count), 0),
                    func.coalesce(func.sum(AIModelMetric.feedback_rating_sum), 0),
                    func.coalesce(func.sum(AIModelMetric.positive_feedback_count), 0),
                    func.coalesce(
                        func.sum(AIModelMetric.accuracy_measurement_count), 0
                    ),
                    func.coalesce(func.sum(AIModelMetric.correct_prediction_count), 0),
                ).where(AIModelMetric.tenant_id == self.tenant_id)
            )
        ).one()
        (
            requests_raw,
            successes_raw,
            errors_raw,
            total_ms_raw,
            feedback_raw,
            rating_sum_raw,
            positive_raw,
            accuracy_count_raw,
            correct_raw,
        ) = row
        requests = int(cast(int, requests_raw) or 0)
        successes = int(cast(int, successes_raw) or 0)
        errors = int(cast(int, errors_raw) or 0)
        total_ms = int(cast(int, total_ms_raw) or 0)
        feedback = int(cast(int, feedback_raw) or 0)
        rating_sum = int(cast(int, rating_sum_raw) or 0)
        positive = int(cast(int, positive_raw) or 0)
        accuracy_count = int(cast(int, accuracy_count_raw) or 0)
        correct = int(cast(int, correct_raw) or 0)
        return AIModelMetricsSummaryResponse(
            total_requests=requests,
            successful_requests=successes,
            failed_requests=errors,
            error_rate=errors / requests if requests else 0.0,
            average_response_time_ms=total_ms / requests if requests else 0.0,
            feedback_count=feedback,
            average_feedback_rating=rating_sum / feedback if feedback else None,
            positive_feedback_rate=positive / feedback if feedback else None,
            accuracy_measurement_count=accuracy_count,
            measured_accuracy_rate=correct / accuracy_count if accuracy_count else None,
        )

    async def submit_feedback(
        self,
        interaction_id: UUID,
        *,
        user_id: UUID,
        rating: int,
        is_accurate: bool | None,
        comment: str | None,
    ) -> AIModelFeedback:
        interaction = await self.db.scalar(
            select(AIInteraction)
            .where(
                AIInteraction.id == interaction_id,
                AIInteraction.tenant_id == self.tenant_id,
            )
            .with_for_update()
        )
        if interaction is None or interaction.user_id != user_id:
            raise not_found("AI interaction")
        if interaction.status != AIInteractionStatus.COMPLETED:
            raise conflict(
                "Feedback can only be submitted for completed AI interactions."
            )
        existing = await self.db.scalar(
            select(AIModelFeedback.id).where(
                AIModelFeedback.tenant_id == self.tenant_id,
                AIModelFeedback.interaction_id == interaction_id,
                AIModelFeedback.user_id == user_id,
            )
        )
        if existing is not None:
            raise conflict("Feedback has already been submitted for this interaction.")

        model_name = metric_model_name(interaction.model)
        model_version = metric_model_version()
        feedback = AIModelFeedback(
            tenant_id=self.tenant_id,
            interaction_id=interaction.id,
            user_id=user_id,
            model_name=model_name,
            model_version=model_version,
            rating=rating,
            is_accurate=is_accurate,
            comment=comment.strip() if comment and comment.strip() else None,
        )
        self.db.add(feedback)
        try:
            await self.db.flush()
            accuracy_increment = 1 if is_accurate is not None else 0
            correct_increment = 1 if is_accurate is True else 0
            statement = insert(AIModelMetric).values(
                tenant_id=self.tenant_id,
                model_name=model_name,
                model_version=model_version,
                request_count=0,
                success_count=0,
                error_count=0,
                total_response_time_ms=0,
                feedback_count=1,
                feedback_rating_sum=rating,
                positive_feedback_count=1 if rating >= 4 else 0,
                accuracy_measurement_count=accuracy_increment,
                correct_prediction_count=correct_increment,
            )
            statement = statement.on_conflict_do_update(
                constraint="uq_ai_model_metrics_tenant_model_version",
                set_={
                    "feedback_count": AIModelMetric.feedback_count + 1,
                    "feedback_rating_sum": AIModelMetric.feedback_rating_sum + rating,
                    "positive_feedback_count": (
                        AIModelMetric.positive_feedback_count
                        + (1 if rating >= 4 else 0)
                    ),
                    "accuracy_measurement_count": (
                        AIModelMetric.accuracy_measurement_count + accuracy_increment
                    ),
                    "correct_prediction_count": (
                        AIModelMetric.correct_prediction_count + correct_increment
                    ),
                    "updated_at": func.now(),
                },
            )
            await self.db.execute(
                statement.execution_options(
                    skip_tenant_filter=True,
                    tenant_scope_reason=(
                        "atomic AI model feedback metric upsert scoped "
                        "by trusted tenant and model key"
                    ),
                )
            )
            await self.db.commit()
            await self.db.refresh(feedback)
            return feedback
        except IntegrityError as exc:
            await self.db.rollback()
            raise conflict(
                "Feedback has already been submitted for this interaction."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise
