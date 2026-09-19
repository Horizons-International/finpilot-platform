from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ai_usage_log import AIUsageLog
from app.repositories.base_repository import BaseRepository


class AIUsageLogRepository(BaseRepository[AIUsageLog]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, AIUsageLog)

    def get_by_user(
        self,
        user_id: UUID,
        *,
        limit: int = 100,
    ) -> list[AIUsageLog]:
        return (
            self.db.query(AIUsageLog)
            .filter(AIUsageLog.user_id == user_id)
            .order_by(AIUsageLog.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_by_feature(
        self,
        feature: str,
        *,
        limit: int = 100,
    ) -> list[AIUsageLog]:
        return (
            self.db.query(AIUsageLog)
            .filter(AIUsageLog.feature == feature)
            .order_by(AIUsageLog.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_recent(
        self,
        *,
        limit: int = 100,
        user_id: UUID | None = None,
        feature: str | None = None,
    ) -> list[AIUsageLog]:
        query = self.db.query(AIUsageLog)

        if user_id is not None:
            query = query.filter(
                AIUsageLog.user_id == user_id,
            )

        if feature is not None:
            query = query.filter(
                AIUsageLog.feature == feature,
            )

        return query.order_by(AIUsageLog.created_at.desc()).limit(limit).all()

    def count(
        self,
        *,
        user_id: UUID | None = None,
        feature: str | None = None,
    ) -> int:
        query = self.db.query(
            func.count(AIUsageLog.id),
        )

        if user_id is not None:
            query = query.filter(
                AIUsageLog.user_id == user_id,
            )

        if feature is not None:
            query = query.filter(
                AIUsageLog.feature == feature,
            )

        return int(query.scalar() or 0)

    def total_input_tokens(
        self,
        *,
        user_id: UUID | None = None,
        feature: str | None = None,
    ) -> int:
        query = self.db.query(
            func.coalesce(
                func.sum(AIUsageLog.input_tokens),
                0,
            ),
        )

        if user_id is not None:
            query = query.filter(
                AIUsageLog.user_id == user_id,
            )

        if feature is not None:
            query = query.filter(
                AIUsageLog.feature == feature,
            )

        return int(query.scalar() or 0)

    def total_output_tokens(
        self,
        *,
        user_id: UUID | None = None,
        feature: str | None = None,
    ) -> int:
        query = self.db.query(
            func.coalesce(
                func.sum(AIUsageLog.output_tokens),
                0,
            ),
        )

        if user_id is not None:
            query = query.filter(
                AIUsageLog.user_id == user_id,
            )

        if feature is not None:
            query = query.filter(
                AIUsageLog.feature == feature,
            )

        return int(query.scalar() or 0)

    def average_response_time(
        self,
        *,
        user_id: UUID | None = None,
        feature: str | None = None,
    ) -> float:
        query = self.db.query(
            func.avg(AIUsageLog.response_time),
        )

        if user_id is not None:
            query = query.filter(
                AIUsageLog.user_id == user_id,
            )

        if feature is not None:
            query = query.filter(
                AIUsageLog.feature == feature,
            )

        value = query.scalar()

        return float(value or 0)

    def error_count(
        self,
        *,
        user_id: UUID | None = None,
        feature: str | None = None,
    ) -> int:
        query = self.db.query(
            func.count(AIUsageLog.id),
        ).filter(
            AIUsageLog.error_message.is_not(None),
        )

        if user_id is not None:
            query = query.filter(
                AIUsageLog.user_id == user_id,
            )

        if feature is not None:
            query = query.filter(
                AIUsageLog.feature == feature,
            )

        return int(query.scalar() or 0)
