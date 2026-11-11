"""Async CRUD and evaluation orchestration for tenant-owned AML rules."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aml_rule import AMLRule
from app.repositories.async_aml_rule_repository import AsyncAMLRuleRepository
from app.schemas.aml_rule import AMLRuleCreate
from app.services.aml_rule_engine import AMLRuleEngine, AMLRuleEvaluationResult
from app.services.async_audit_service import AsyncAuditService
from app.utils.enums import AMLRuleStatus, AMLRuleType, AuditEventType
from app.utils.errors import bad_request, not_found


class AsyncAMLRuleService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.db.info["tenant_id"] = tenant_id
        self.repository = AsyncAMLRuleRepository(db, tenant_id)
        self.engine = AMLRuleEngine()
        self.audit_service = AsyncAuditService(db)

    async def create(
        self,
        *,
        data: AMLRuleCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AMLRule:
        try:
            self.engine.validate_condition(data.condition)
        except ValueError as exc:
            raise bad_request(str(exc)) from exc

        rule = await self.repository.create(
            AMLRule(
                tenant_id=self.tenant_id,
                name=data.name,
                description=data.description,
                rule_type=data.rule_type,
                condition=data.condition,
                severity=data.severity,
                status=data.status,
            )
        )
        await self.audit_service.log_event(
            user_id=user_id,
            email=email,
            event_type=AuditEventType.AML_RULE_CREATED,
            resource_type="aml_rule",
            resource_id=rule.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def list_all(self) -> list[AMLRule]:
        return await self.repository.get_all()

    async def get_by_id(self, rule_id: UUID) -> AMLRule:
        rule = await self.repository.get_by_id(rule_id)
        if rule is None:
            raise not_found("AML rule")
        return rule

    async def update_status(
        self,
        *,
        rule_id: UUID,
        new_status: AMLRuleStatus,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AMLRule:
        rule = await self.get_by_id(rule_id)
        if rule.status == new_status:
            raise bad_request("AML rule is already in the requested status.")
        rule.status = new_status
        rule = await self.repository.update(rule)
        await self.audit_service.log_event(
            user_id=user_id,
            email=email,
            event_type=AuditEventType.AML_RULE_STATUS_CHANGED,
            resource_type="aml_rule",
            resource_id=rule.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def evaluate(
        self,
        *,
        rule_type: AMLRuleType,
        data: dict[str, Any],
        user_id: UUID | None = None,
        email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AMLRuleEvaluationResult:
        rules = await self.repository.get_active_by_type(rule_type)
        result = self.engine.evaluate(rule_type=rule_type, rules=rules, data=data)
        if user_id is not None and email is not None:
            for evaluation in result.evaluations:
                await self.audit_service.log_event(
                    user_id=user_id,
                    email=email,
                    event_type=AuditEventType.AML_RULE_EVALUATED,
                    resource_type="aml_rule",
                    resource_id=evaluation.rule_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
        await self.db.commit()
        return result
