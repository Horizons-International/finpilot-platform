from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.risk_scoring_rule import RiskScoringRule


class RiskScoringRuleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        rule: RiskScoringRule,
    ) -> RiskScoringRule:
        self.db.add(rule)
        self.db.flush()
        self.db.refresh(rule)

        return rule

    def get_by_id(
        self,
        rule_id: UUID,
    ) -> RiskScoringRule | None:
        return self.db.scalar(
            select(RiskScoringRule).where(
                RiskScoringRule.id == rule_id,
            )
        )

    def get_all(
        self,
    ) -> list[RiskScoringRule]:
        statement = select(RiskScoringRule).order_by(
            RiskScoringRule.priority.asc(),
            RiskScoringRule.factor_key.asc(),
        )

        return list(self.db.scalars(statement).all())

    def get_active_rules(
        self,
    ) -> list[RiskScoringRule]:
        statement = (
            select(RiskScoringRule)
            .where(
                RiskScoringRule.is_active.is_(True),
            )
            .order_by(
                RiskScoringRule.priority.asc(),
                RiskScoringRule.factor_key.asc(),
            )
        )

        return list(self.db.scalars(statement).all())

    def update(
        self,
        rule: RiskScoringRule,
    ) -> RiskScoringRule:
        self.db.flush()
        self.db.refresh(rule)

        return rule

    def delete(
        self,
        rule: RiskScoringRule,
    ) -> None:
        self.db.delete(rule)
        self.db.flush()
