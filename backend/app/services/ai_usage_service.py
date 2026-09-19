from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.models.ai_usage_log import AIUsageLog
from app.repositories.ai_usage_log_repository import (
    AIUsageLogRepository,
)
from app.schemas.ai_usage import (
    AIUsageListResponse,
    AIUsageLogResponse,
    AIUsageSummaryResponse,
)

logger = get_logger(__name__)


class AIUsageService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AIUsageLogRepository(db)

    def record(
        self,
        *,
        user_id: UUID,
        feature: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        response_time: int,
        error_message: str | None = None,
        commit: bool = True,
    ) -> AIUsageLog:
        usage_log = AIUsageLog(
            user_id=user_id,
            feature=feature,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            response_time=response_time,
            error_message=error_message,
        )

        self.repository.create(usage_log)

        if commit:
            self.db.commit()
            self.db.refresh(usage_log)

        logger.info(
            "AI usage recorded: user_id=%s feature=%s model=%s "
            "input_tokens=%s output_tokens=%s response_time_ms=%s "
            "error=%s",
            user_id,
            feature,
            model,
            input_tokens,
            output_tokens,
            response_time,
            error_message is not None,
        )

        return usage_log

    def get_usage(
        self,
        *,
        limit: int = 100,
        user_id: UUID | None = None,
        feature: str | None = None,
    ) -> AIUsageListResponse:
        usage_logs = self.repository.get_recent(
            limit=limit,
            user_id=user_id,
            feature=feature,
        )

        total = self.repository.count(
            user_id=user_id,
            feature=feature,
        )

        return AIUsageListResponse(
            items=[
                AIUsageLogResponse.model_validate(
                    usage_log,
                )
                for usage_log in usage_logs
            ],
            total=total,
        )

    def get_summary(
        self,
        *,
        user_id: UUID | None = None,
        feature: str | None = None,
    ) -> AIUsageSummaryResponse:
        total_requests = self.repository.count(
            user_id=user_id,
            feature=feature,
        )

        total_errors = self.repository.error_count(
            user_id=user_id,
            feature=feature,
        )

        total_input_tokens = self.repository.total_input_tokens(
            user_id=user_id,
            feature=feature,
        )

        total_output_tokens = self.repository.total_output_tokens(
            user_id=user_id,
            feature=feature,
        )

        average_response_time = self.repository.average_response_time(
            user_id=user_id,
            feature=feature,
        )

        return AIUsageSummaryResponse(
            total_requests=total_requests,
            total_errors=total_errors,
            successful_requests=(total_requests - total_errors),
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            average_response_time=average_response_time,
        )
