"""Tenant-scoped async persistence for AML monitoring results."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aml_rule import AMLRule
from app.models.customer import Customer
from app.models.transaction_monitoring_result import TransactionMonitoringResult
from app.repositories.async_tenant_scoped_repository import (
    AsyncTenantScopedRepository,
)


class AsyncTransactionMonitoringResultRepository(
    AsyncTenantScopedRepository[TransactionMonitoringResult]
):
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(db=db, model=TransactionMonitoringResult, tenant_id=tenant_id)

    async def create(
        self, entity: TransactionMonitoringResult
    ) -> TransactionMonitoringResult:
        if entity.tenant_id is not None and entity.tenant_id != self.tenant_id:
            raise ValueError("Cannot create a monitoring result for another tenant.")
        customer_exists = await self.db.scalar(
            select(Customer.id).where(
                Customer.id == entity.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer_exists is None:
            raise ValueError("Monitoring result customer is outside this tenant.")
        rule_exists = await self.db.scalar(
            select(AMLRule.id).where(
                AMLRule.id == entity.rule_id,
                AMLRule.tenant_id == self.tenant_id,
            )
        )
        if rule_exists is None:
            raise ValueError("Monitoring rule is outside this tenant.")
        return await super().create(entity)

    async def get_by_transaction_id(
        self, transaction_id: UUID
    ) -> list[TransactionMonitoringResult]:
        statement = (
            self.query()
            .where(TransactionMonitoringResult.transaction_id == transaction_id)
            .order_by(TransactionMonitoringResult.created_at.desc())
        )
        return list((await self.db.scalars(statement)).all())
