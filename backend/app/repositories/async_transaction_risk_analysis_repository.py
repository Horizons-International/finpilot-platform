"""Tenant-scoped async persistence for transaction-risk assessments."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.transaction_risk_analysis import (
    TransactionRiskAnalysis,
    TransactionRiskTransaction,
)
from app.models.verification_case import IdentityVerificationCase
from app.repositories.async_tenant_scoped_repository import (
    AsyncTenantScopedRepository,
)


class AsyncTransactionRiskAnalysisRepository(
    AsyncTenantScopedRepository[TransactionRiskAnalysis]
):
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(db, TransactionRiskAnalysis, tenant_id)

    async def get_customer(self, customer_id: UUID) -> Customer | None:
        return await self.db.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )

    async def get_risk_profile(self, customer_id: UUID) -> CustomerRiskProfile | None:
        return await self.db.scalar(
            select(CustomerRiskProfile).where(
                CustomerRiskProfile.tenant_id == self.tenant_id,
                CustomerRiskProfile.customer_id == customer_id,
            )
        )

    async def list_verification_cases(
        self, customer_id: UUID, *, limit: int = 100
    ) -> list[IdentityVerificationCase]:
        result = await self.db.scalars(
            select(IdentityVerificationCase)
            .where(
                IdentityVerificationCase.tenant_id == self.tenant_id,
                IdentityVerificationCase.customer_id == customer_id,
            )
            .order_by(IdentityVerificationCase.created_at.desc())
            .limit(limit)
        )
        return list(result.all())

    async def list_compliance_cases(
        self, customer_id: UUID, *, limit: int = 20
    ) -> list[ComplianceCase]:
        result = await self.db.scalars(
            select(ComplianceCase)
            .where(
                ComplianceCase.tenant_id == self.tenant_id,
                ComplianceCase.customer_id == customer_id,
            )
            .order_by(ComplianceCase.created_at.desc())
            .limit(limit)
        )
        return list(result.all())

    async def list_historical_transactions(
        self,
        customer_id: UUID,
        *,
        start_at: datetime,
        end_at: datetime,
        limit: int = 1000,
    ) -> list[TransactionRiskTransaction]:
        result = await self.db.scalars(
            select(TransactionRiskTransaction)
            .where(
                TransactionRiskTransaction.tenant_id == self.tenant_id,
                TransactionRiskTransaction.customer_id == customer_id,
                TransactionRiskTransaction.occurred_at >= start_at,
                TransactionRiskTransaction.occurred_at < end_at,
            )
            .order_by(TransactionRiskTransaction.occurred_at.desc())
            .limit(limit)
        )
        return list(result.all())

    async def get_existing_transaction_ids(
        self, transaction_ids: list[UUID]
    ) -> set[UUID]:
        if not transaction_ids:
            return set()
        result = await self.db.scalars(
            select(TransactionRiskTransaction.transaction_id).where(
                TransactionRiskTransaction.tenant_id == self.tenant_id,
                TransactionRiskTransaction.transaction_id.in_(transaction_ids),
            )
        )
        return set(result.all())

    async def list_analyses(
        self, *, customer_id: UUID | None = None, limit: int = 100
    ) -> list[TransactionRiskAnalysis]:
        statement = self.query()
        if customer_id is not None:
            statement = statement.where(
                TransactionRiskAnalysis.customer_id == customer_id
            )
        result = await self.db.scalars(
            statement.order_by(TransactionRiskAnalysis.created_at.desc()).limit(limit)
        )
        return list(result.all())
