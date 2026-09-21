from uuid import UUID

from sqlalchemy.orm import Session

from app.models.risk_scoring_rule import RiskScoringRule
from app.repositories.base_repository import BaseRepository


class RiskScoringRuleRepository(BaseRepository[RiskScoringRule]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, RiskScoringRule)

    def get_active_rules(self) -> list[RiskScoringRule]:
        return (
            self.db.query(RiskScoringRule)
            .filter(RiskScoringRule.is_active.is_(True))
            .order_by(
                RiskScoringRule.priority.asc(),
                RiskScoringRule.created_at.asc(),
            )
            .all()
        )

    def get_by_id(
        self,
        rule_id: UUID,
    ) -> RiskScoringRule | None:
        return (
            self.db.query(RiskScoringRule).filter(RiskScoringRule.id == rule_id).first()
        )
