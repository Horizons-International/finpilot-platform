from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ai_usage_log import AIUsageLog
from app.models.user import User
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class AIUsageLogRepository(TenantScopedRepository[AIUsageLog]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved_tenant_id = tenant_id or db.info.get("tenant_id")
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for AI usage logs.")

        super().__init__(db, AIUsageLog, resolved_tenant_id)

    def _ensure_user_belongs_to_tenant(self, user_id: UUID) -> None:
        user_exists = (
            self.db.query(User.id)
            .filter(
                User.id == user_id,
                User.tenant_id == self.tenant_id,
            )
            .first()
        )
        if user_exists is None:
            raise ValueError("The AI usage log user does not belong to this tenant.")

    def create(self, log: AIUsageLog) -> AIUsageLog:
        self._ensure_user_belongs_to_tenant(log.user_id)
        return super().create(log)

    def update(self, log: AIUsageLog) -> AIUsageLog:
        self._ensure_user_belongs_to_tenant(log.user_id)
        return super().update(log)

    def get_by_user(
        self,
        user_id: UUID,
        *,
        limit: int = 100,
    ) -> list[AIUsageLog]:
        return (
            self.query()
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
            self.query()
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
        query = self.query()
        if user_id is not None:
            query = query.filter(AIUsageLog.user_id == user_id)
        if feature is not None:
            query = query.filter(AIUsageLog.feature == feature)
        return query.order_by(AIUsageLog.created_at.desc()).limit(limit).all()

    def count(
        self,
        *,
        user_id: UUID | None = None,
        feature: str | None = None,
    ) -> int:
        query = self.query().with_entities(func.count(AIUsageLog.id))
        if user_id is not None:
            query = query.filter(AIUsageLog.user_id == user_id)
        if feature is not None:
            query = query.filter(AIUsageLog.feature == feature)
        return int(query.scalar() or 0)

    def total_input_tokens(
        self,
        *,
        user_id: UUID | None = None,
        feature: str | None = None,
    ) -> int:
        query = self.query().with_entities(
            func.coalesce(func.sum(AIUsageLog.input_tokens), 0)
        )
        if user_id is not None:
            query = query.filter(AIUsageLog.user_id == user_id)
        if feature is not None:
            query = query.filter(AIUsageLog.feature == feature)
        return int(query.scalar() or 0)

    def total_output_tokens(
        self,
        *,
        user_id: UUID | None = None,
        feature: str | None = None,
    ) -> int:
        query = self.query().with_entities(
            func.coalesce(func.sum(AIUsageLog.output_tokens), 0)
        )
        if user_id is not None:
            query = query.filter(AIUsageLog.user_id == user_id)
        if feature is not None:
            query = query.filter(AIUsageLog.feature == feature)
        return int(query.scalar() or 0)

    def average_response_time(
        self,
        *,
        user_id: UUID | None = None,
        feature: str | None = None,
    ) -> float:
        query = self.query().with_entities(func.avg(AIUsageLog.response_time))
        if user_id is not None:
            query = query.filter(AIUsageLog.user_id == user_id)
        if feature is not None:
            query = query.filter(AIUsageLog.feature == feature)
        return float(query.scalar() or 0)

    def error_count(
        self,
        *,
        user_id: UUID | None = None,
        feature: str | None = None,
    ) -> int:
        query = (
            self.query()
            .with_entities(func.count(AIUsageLog.id))
            .filter(AIUsageLog.error_message.is_not(None))
        )
        if user_id is not None:
            query = query.filter(AIUsageLog.user_id == user_id)
        if feature is not None:
            query = query.filter(AIUsageLog.feature == feature)
        return int(query.scalar() or 0)
