"""Tenant-scoped async access to AML rules."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aml_rule import AMLRule
from app.repositories.async_tenant_scoped_repository import (
    AsyncTenantScopedRepository,
)
from app.utils.enums import AMLRuleStatus, AMLRuleType


class AsyncAMLRuleRepository(AsyncTenantScopedRepository[AMLRule]):
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(db=db, model=AMLRule, tenant_id=tenant_id)

    async def get_by_id(self, rule_id: UUID) -> AMLRule | None:
        return await self.db.scalar(self.query().where(AMLRule.id == rule_id))

    async def get_all(self) -> list[AMLRule]:
        statement = self.query().order_by(AMLRule.name.asc())
        return list((await self.db.scalars(statement)).all())

    async def get_active_by_type(self, rule_type: AMLRuleType) -> list[AMLRule]:
        statement = (
            self.query()
            .where(
                AMLRule.rule_type == rule_type,
                AMLRule.status == AMLRuleStatus.ACTIVE,
            )
            .order_by(AMLRule.name.asc())
        )
        return list((await self.db.scalars(statement)).all())
