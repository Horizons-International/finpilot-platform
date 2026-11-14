"""Tenant-scoped asynchronous reads for persisted AI decision explanations."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_decision_explanation import AIDecisionExplanation
from app.repositories.async_ai_decision_explanation_repository import (
    AsyncAIDecisionExplanationRepository,
)
from app.repositories.async_tenant_scoped_repository import resolve_async_tenant_id
from app.utils.errors import bad_request, not_found

SUPPORTED_DECISION_TYPES = frozenset(
    {
        "CASE_PRIORITY",
        "AI_RISK_RECOMMENDATION",
        "TRANSACTION_RISK_ANALYSIS",
        "DOCUMENT_FRAUD_ANALYSIS",
        "AML_INVESTIGATION_ANALYSIS",
        "AI_INTERACTION",
    }
)


class AsyncAIDecisionExplanationService:
    def __init__(self, db: AsyncSession, *, tenant_id: UUID) -> None:
        resolved_tenant_id = resolve_async_tenant_id(db, tenant_id)
        assert resolved_tenant_id is not None
        db.info["tenant_id"] = resolved_tenant_id
        self.tenant_id = resolved_tenant_id
        self.repository = AsyncAIDecisionExplanationRepository(
            db, tenant_id=self.tenant_id
        )

    @staticmethod
    def _validate_decision_type(decision_type: str) -> str:
        value = decision_type.strip().upper()
        if value not in SUPPORTED_DECISION_TYPES:
            raise bad_request(
                "Unsupported decision type. Supported types are: "
                + ", ".join(sorted(SUPPORTED_DECISION_TYPES))
                + "."
            )
        return value

    async def get_latest(
        self, decision_type: str, decision_id: UUID
    ) -> AIDecisionExplanation:
        kind = self._validate_decision_type(decision_type)
        explanation = await self.repository.get_latest(kind, decision_id)
        if explanation is None:
            raise not_found("AI decision explanation")
        return explanation

    async def get_history(
        self,
        decision_type: str,
        decision_id: UUID,
        *,
        limit: int = 100,
    ) -> tuple[list[AIDecisionExplanation], int]:
        kind = self._validate_decision_type(decision_type)
        items = await self.repository.get_history(kind, decision_id, limit=limit)
        if not items:
            raise not_found("AI decision explanation history")
        total = await self.repository.count_history(kind, decision_id)
        return items, total
