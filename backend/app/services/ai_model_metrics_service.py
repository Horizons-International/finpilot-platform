"""Read model performance metrics and capture interaction feedback."""

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ai_model_feedback import AIModelFeedback
from app.models.ai_model_metric import AIModelMetric
from app.repositories.ai_interaction_repository import AIInteractionRepository
from app.schemas.ai_model_metrics import (
    AIModelMetricResponse,
    AIModelMetricsSummaryResponse,
)
from app.services.ai_model_metric_recorder import (
    metric_model_name,
    metric_model_version,
)
from app.services.tenant_context import resolve_tenant_context
from app.utils.enums import AIInteractionStatus
from app.utils.errors import conflict, not_found


class AIModelMetricsService:
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = resolve_tenant_context(
            db, tenant_id, resource_name="AI model metrics"
        )
        self.interactions = AIInteractionRepository(db, tenant_id=self.tenant_id)

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

    def list_metrics(
        self, *, model_name: str | None = None, model_version: str | None = None
    ) -> list[AIModelMetricResponse]:
        query = self.db.query(AIModelMetric).filter(
            AIModelMetric.tenant_id == self.tenant_id
        )
        if model_name:
            query = query.filter(AIModelMetric.model_name == model_name)
        if model_version:
            query = query.filter(AIModelMetric.model_version == model_version)
        metrics = query.order_by(AIModelMetric.updated_at.desc()).all()
        return [self._response(metric) for metric in metrics]

    def get_summary(self) -> AIModelMetricsSummaryResponse:
        row = (
            self.db.query(
                func.coalesce(func.sum(AIModelMetric.request_count), 0),
                func.coalesce(func.sum(AIModelMetric.success_count), 0),
                func.coalesce(func.sum(AIModelMetric.error_count), 0),
                func.coalesce(func.sum(AIModelMetric.total_response_time_ms), 0),
                func.coalesce(func.sum(AIModelMetric.feedback_count), 0),
                func.coalesce(func.sum(AIModelMetric.feedback_rating_sum), 0),
                func.coalesce(func.sum(AIModelMetric.positive_feedback_count), 0),
                func.coalesce(func.sum(AIModelMetric.accuracy_measurement_count), 0),
                func.coalesce(func.sum(AIModelMetric.correct_prediction_count), 0),
            )
            .filter(AIModelMetric.tenant_id == self.tenant_id)
            .one()
        )
        (
            requests,
            successes,
            errors,
            total_ms,
            feedback,
            rating_sum,
            positive,
            accuracy_count,
            correct,
        ) = (int(value or 0) for value in row)
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

    def submit_feedback(
        self,
        interaction_id: UUID,
        *,
        user_id: UUID,
        rating: int,
        is_accurate: bool | None,
        comment: str | None,
    ) -> AIModelFeedback:
        interaction = self.interactions.get_by_id(interaction_id)
        if interaction is None:
            raise not_found("AI interaction")
        if interaction.user_id != user_id:
            # A caller may only provide feedback on their own AI response.
            raise not_found("AI interaction")
        if interaction.status != AIInteractionStatus.COMPLETED:
            raise conflict(
                "Feedback can only be submitted for completed AI interactions."
            )
        existing = (
            self.db.query(AIModelFeedback)
            .filter(
                AIModelFeedback.tenant_id == self.tenant_id,
                AIModelFeedback.interaction_id == interaction_id,
                AIModelFeedback.user_id == user_id,
            )
            .first()
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

        metric = (
            self.db.query(AIModelMetric)
            .filter(
                AIModelMetric.tenant_id == self.tenant_id,
                AIModelMetric.model_name == model_name,
                AIModelMetric.model_version == model_version,
            )
            .with_for_update()
            .first()
        )
        if metric is None:
            # Existing interactions may predate this monitoring migration.
            metric = AIModelMetric(
                tenant_id=self.tenant_id,
                model_name=model_name,
                model_version=model_version,
            )
            self.db.add(metric)
            self.db.flush()
        metric.feedback_count += 1
        metric.feedback_rating_sum += rating
        if rating >= 4:
            metric.positive_feedback_count += 1
        if is_accurate is not None:
            metric.accuracy_measurement_count += 1
            if is_accurate:
                metric.correct_prediction_count += 1
        self.db.commit()
        self.db.refresh(feedback)
        return feedback
