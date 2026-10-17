"""Tenant-scoped reads for persisted AI decision explanations."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.ai_decision_explanation import AIDecisionExplanation
from app.repositories.ai_decision_explanation_repository import (
    AIDecisionExplanationRepository,
)
from app.services.tenant_context import resolve_tenant_context
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


class AIDecisionExplanationService:
    def __init__(self, db: Session, *, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = resolve_tenant_context(
            db, tenant_id, resource_name="AI decision explanations"
        )
        self.repository = AIDecisionExplanationRepository(db, tenant_id=self.tenant_id)

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

    def get_latest(
        self, decision_type: str, decision_id: UUID
    ) -> AIDecisionExplanation:
        kind = self._validate_decision_type(decision_type)
        explanation = self.repository.get_latest(kind, decision_id)
        if explanation is None:
            raise not_found("AI decision explanation")
        return explanation

    def get_history(
        self,
        decision_type: str,
        decision_id: UUID,
        *,
        limit: int = 100,
    ) -> tuple[list[AIDecisionExplanation], int]:
        kind = self._validate_decision_type(decision_type)
        items = self.repository.get_history(kind, decision_id, limit=limit)
        if not items:
            raise not_found("AI decision explanation history")
        return items, self.repository.count_history(kind, decision_id)
