"""Async tenant-scoped queries for persisted AI decision explanations."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_decision_explanation import AIDecisionExplanation
from app.repositories.async_tenant_scoped_repository import AsyncTenantScopedRepository


class AsyncAIDecisionExplanationRepository(
    AsyncTenantScopedRepository[AIDecisionExplanation]
):
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(db, AIDecisionExplanation, tenant_id)

    async def get_latest(
        self,
        decision_type: str,
        decision_id: UUID,
    ) -> AIDecisionExplanation | None:
        statement = (
            self.query()
            .where(
                AIDecisionExplanation.decision_type == decision_type,
                AIDecisionExplanation.decision_id == decision_id,
            )
            .order_by(AIDecisionExplanation.created_at.desc())
            .limit(1)
        )
        return await self.db.scalar(statement)

    async def get_history(
        self,
        decision_type: str,
        decision_id: UUID,
        *,
        limit: int = 100,
    ) -> list[AIDecisionExplanation]:
        statement = (
            self.query()
            .where(
                AIDecisionExplanation.decision_type == decision_type,
                AIDecisionExplanation.decision_id == decision_id,
            )
            .order_by(AIDecisionExplanation.created_at.desc())
            .limit(limit)
        )
        result = await self.db.scalars(statement)
        return list(result.all())

    async def count_history(self, decision_type: str, decision_id: UUID) -> int:
        statement = select(func.count(AIDecisionExplanation.id)).where(
            AIDecisionExplanation.tenant_id == self.tenant_id,
            AIDecisionExplanation.decision_type == decision_type,
            AIDecisionExplanation.decision_id == decision_id,
        )
        return int(await self.db.scalar(statement) or 0)
