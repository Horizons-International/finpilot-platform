from uuid import UUID

from sqlalchemy.orm import Session

from app.models.ai_decision_explanation import AIDecisionExplanation
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class AIDecisionExplanationRepository(TenantScopedRepository[AIDecisionExplanation]):
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(db, AIDecisionExplanation, tenant_id)

    def get_latest(
        self,
        decision_type: str,
        decision_id: UUID,
    ) -> AIDecisionExplanation | None:
        return (
            self.query()
            .filter(
                AIDecisionExplanation.decision_type == decision_type,
                AIDecisionExplanation.decision_id == decision_id,
            )
            .order_by(AIDecisionExplanation.created_at.desc())
            .first()
        )

    def get_history(
        self,
        decision_type: str,
        decision_id: UUID,
        *,
        limit: int = 100,
    ) -> list[AIDecisionExplanation]:
        return (
            self.query()
            .filter(
                AIDecisionExplanation.decision_type == decision_type,
                AIDecisionExplanation.decision_id == decision_id,
            )
            .order_by(AIDecisionExplanation.created_at.desc())
            .limit(limit)
            .all()
        )

    def count_history(self, decision_type: str, decision_id: UUID) -> int:
        return int(
            self.query()
            .filter(
                AIDecisionExplanation.decision_type == decision_type,
                AIDecisionExplanation.decision_id == decision_id,
            )
            .count()
        )
