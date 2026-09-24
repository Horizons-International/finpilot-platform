from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.aml_rule import AMLRule
from app.utils.enums import AMLRuleStatus, AMLRuleType


class AMLRuleRepository:
    def __init__(
        self,
        db: Session,
    ) -> None:
        self.db = db

    def create(
        self,
        rule: AMLRule,
    ) -> AMLRule:
        self.db.add(rule)
        self.db.flush()
        self.db.refresh(rule)

        return rule

    def get_by_id(
        self,
        rule_id: UUID,
    ) -> AMLRule | None:
        return self.db.scalar(
            select(AMLRule).where(
                AMLRule.id == rule_id,
            )
        )

    def get_all(
        self,
    ) -> list[AMLRule]:
        statement = select(AMLRule).order_by(
            AMLRule.name.asc(),
        )

        return list(self.db.scalars(statement).all())

    def get_active_by_type(
        self,
        rule_type: AMLRuleType,
    ) -> list[AMLRule]:
        statement = (
            select(AMLRule)
            .where(
                AMLRule.rule_type == rule_type,
                AMLRule.status == AMLRuleStatus.ACTIVE,
            )
            .order_by(
                AMLRule.name.asc(),
            )
        )

        return list(self.db.scalars(statement).all())

    def update(
        self,
        rule: AMLRule,
    ) -> AMLRule:
        self.db.flush()
        self.db.refresh(rule)

        return rule
