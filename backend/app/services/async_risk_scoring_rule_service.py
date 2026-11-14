"""Native-async management for tenant-scoped customer risk-scoring rules."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk_scoring_rule import RiskScoringRule
from app.schemas.risk_scoring import RiskScoringRuleCreate, RiskScoringRuleUpdate
from app.services.async_audit_service import AsyncAuditService
from app.utils.enums import AuditEventType
from app.utils.errors import bad_request, not_found


class AsyncRiskScoringRuleService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active = db.info.get("tenant_id")
        if active is not None and active != tenant_id:
            raise ValueError("Risk-scoring rule tenant does not match the session.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.audit = AsyncAuditService(db)

    async def _get(self, rule_id: UUID, *, for_update: bool = False) -> RiskScoringRule:
        statement = select(RiskScoringRule).where(
            RiskScoringRule.id == rule_id,
            RiskScoringRule.tenant_id == self.tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        rule = await self.db.scalar(statement)
        if rule is None:
            raise not_found("Risk scoring rule")
        return rule

    async def create(
        self,
        *,
        data: RiskScoringRuleCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> RiskScoringRule:
        rule = RiskScoringRule(
            tenant_id=self.tenant_id,
            factor_key=data.factor_key,
            operator=data.operator,
            expected_value=data.expected_value,
            score_points=data.score_points,
            description=data.description,
            priority=data.priority,
            is_active=data.is_active,
        )
        self.db.add(rule)
        await self.db.flush()
        await self.audit.log_event(
            event_type=AuditEventType.RISK_SCORING_RULE_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="risk_scoring_rule",
            resource_id=rule.id,
        )
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def list_all(self) -> list[RiskScoringRule]:
        result = await self.db.scalars(
            select(RiskScoringRule)
            .where(RiskScoringRule.tenant_id == self.tenant_id)
            .order_by(RiskScoringRule.priority.asc(), RiskScoringRule.factor_key.asc())
        )
        return list(result.all())

    async def get_by_id(self, rule_id: UUID) -> RiskScoringRule:
        return await self._get(rule_id)

    async def update(
        self,
        *,
        rule_id: UUID,
        data: RiskScoringRuleUpdate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> RiskScoringRule:
        rule = await self._get(rule_id, for_update=True)
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise bad_request("At least one field must be provided for update.")
        for field, value in update_data.items():
            if field not in {"tenant_id", "id"}:
                setattr(rule, field, value)
        await self.db.flush()
        await self.audit.log_event(
            event_type=AuditEventType.RISK_SCORING_RULE_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="risk_scoring_rule",
            resource_id=rule.id,
        )
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def update_status(
        self,
        *,
        rule_id: UUID,
        is_active: bool,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> RiskScoringRule:
        rule = await self._get(rule_id, for_update=True)
        if rule.is_active == is_active:
            raise bad_request("Risk scoring rule is already in this status.")
        rule.is_active = is_active
        await self.db.flush()
        await self.audit.log_event(
            event_type=AuditEventType.RISK_SCORING_RULE_STATUS_CHANGED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="risk_scoring_rule",
            resource_id=rule.id,
        )
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def delete(
        self,
        *,
        rule_id: UUID,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        rule = await self._get(rule_id, for_update=True)
        await self.db.delete(rule)
        await self.audit.log_event(
            event_type=AuditEventType.RISK_SCORING_RULE_DELETED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="risk_scoring_rule",
            resource_id=rule.id,
        )
        await self.db.commit()
