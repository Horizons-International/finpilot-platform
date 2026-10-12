from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.risk_scoring_rule import RiskScoringRule
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class RiskScoringRuleRepository(TenantScopedRepository[RiskScoringRule]):
    """Tenant-scoped scoring rules."""

    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved_tenant_id = tenant_id or db.info.get("tenant_id")
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for risk scoring rules.")
        session_tenant_id = db.info.get("tenant_id")
        if session_tenant_id is not None and session_tenant_id != resolved_tenant_id:
            raise ValueError(
                "The SQLAlchemy session is already bound to another tenant."
            )
        # Also scope relationship/lazy loads covered by tenant_filter.py.
        db.info["tenant_id"] = resolved_tenant_id
        super().__init__(db=db, model=RiskScoringRule, tenant_id=resolved_tenant_id)

    def get_by_id(self, rule_id: UUID) -> RiskScoringRule | None:
        return self.query().filter(RiskScoringRule.id == rule_id).first()

    def get_all(self) -> list[RiskScoringRule]:
        return (
            self.query()
            .order_by(
                RiskScoringRule.priority.asc(),
                RiskScoringRule.factor_key.asc(),
            )
            .all()
        )

    def get_active_rules(self) -> list[RiskScoringRule]:
        return (
            self.query()
            .filter(RiskScoringRule.is_active.is_(True))
            .order_by(
                RiskScoringRule.priority.asc(),
                RiskScoringRule.factor_key.asc(),
            )
            .all()
        )

    def _assert_owned(self, rule: RiskScoringRule) -> None:
        if rule.tenant_id != self.tenant_id:
            raise ValueError("Risk scoring rule belongs to another tenant.")
        exists = self.db.scalar(
            select(RiskScoringRule.id).where(
                RiskScoringRule.id == rule.id,
                RiskScoringRule.tenant_id == self.tenant_id,
            )
        )
        if exists is None:
            raise ValueError("Risk scoring rule does not belong to the current tenant.")

    def update(self, rule: RiskScoringRule) -> RiskScoringRule:
        self._assert_owned(rule)
        self.db.flush()
        self.db.refresh(rule)
        return rule

    def delete(self, rule: RiskScoringRule) -> None:
        self._assert_owned(rule)
        self.db.delete(rule)
        self.db.flush()
