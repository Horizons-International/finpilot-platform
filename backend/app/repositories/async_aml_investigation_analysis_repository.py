"""Native-async, tenant-scoped persistence for AML investigation analyses."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aml_investigation_analysis import AMLInvestigationAnalysis
from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.transaction_anomaly import (
    TransactionAnomaly,
    TransactionAnomalyActivity,
)
from app.models.transaction_monitoring_result import TransactionMonitoringResult
from app.models.transaction_risk_analysis import (
    TransactionRiskAnalysis,
    TransactionRiskTransaction,
)
from app.models.verification_case import IdentityVerificationCase
from app.repositories.async_tenant_scoped_repository import (
    AsyncTenantScopedRepository,
)


class AsyncAMLInvestigationAnalysisRepository(
    AsyncTenantScopedRepository[AMLInvestigationAnalysis]
):
    """All investigation evidence and history reads are tenant restricted."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(db=db, model=AMLInvestigationAnalysis, tenant_id=tenant_id)

    async def get_analysis(self, analysis_id: UUID) -> AMLInvestigationAnalysis | None:
        return await self.get_by_id(analysis_id)

    async def get_compliance_case(self, case_id: UUID) -> ComplianceCase | None:
        return await self.db.scalar(
            select(ComplianceCase).where(
                ComplianceCase.id == case_id,
                ComplianceCase.tenant_id == self.tenant_id,
            )
        )

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

    async def list_compliance_cases(self, customer_id: UUID) -> list[ComplianceCase]:
        statement = (
            select(ComplianceCase)
            .where(
                ComplianceCase.tenant_id == self.tenant_id,
                ComplianceCase.customer_id == customer_id,
            )
            .order_by(ComplianceCase.created_at.desc())
            .limit(10)
        )
        return list((await self.db.scalars(statement)).all())

    async def list_verification_cases(
        self, customer_id: UUID
    ) -> list[IdentityVerificationCase]:
        statement = (
            select(IdentityVerificationCase)
            .where(
                IdentityVerificationCase.tenant_id == self.tenant_id,
                IdentityVerificationCase.customer_id == customer_id,
            )
            .order_by(IdentityVerificationCase.created_at.desc())
            .limit(10)
        )
        return list((await self.db.scalars(statement)).all())

    async def list_transaction_activity(
        self, customer_id: UUID
    ) -> list[TransactionAnomalyActivity]:
        statement = (
            select(TransactionAnomalyActivity)
            .where(
                TransactionAnomalyActivity.tenant_id == self.tenant_id,
                TransactionAnomalyActivity.customer_id == customer_id,
            )
            .order_by(TransactionAnomalyActivity.occurred_at.desc())
            .limit(50)
        )
        return list((await self.db.scalars(statement)).all())

    async def list_transaction_risk_transactions(
        self, customer_id: UUID
    ) -> list[TransactionRiskTransaction]:
        statement = (
            select(TransactionRiskTransaction)
            .where(
                TransactionRiskTransaction.tenant_id == self.tenant_id,
                TransactionRiskTransaction.customer_id == customer_id,
            )
            .order_by(TransactionRiskTransaction.occurred_at.desc())
            .limit(50)
        )
        return list((await self.db.scalars(statement)).all())

    async def list_transaction_risk_analyses(
        self, customer_id: UUID
    ) -> list[TransactionRiskAnalysis]:
        statement = (
            select(TransactionRiskAnalysis)
            .where(
                TransactionRiskAnalysis.tenant_id == self.tenant_id,
                TransactionRiskAnalysis.customer_id == customer_id,
            )
            .order_by(TransactionRiskAnalysis.created_at.desc())
            .limit(10)
        )
        return list((await self.db.scalars(statement)).all())

    async def list_anomalies(self, customer_id: UUID) -> list[TransactionAnomaly]:
        statement = (
            select(TransactionAnomaly)
            .where(
                TransactionAnomaly.tenant_id == self.tenant_id,
                TransactionAnomaly.customer_id == customer_id,
            )
            .order_by(TransactionAnomaly.created_at.desc())
            .limit(20)
        )
        return list((await self.db.scalars(statement)).all())

    async def list_monitoring_results(
        self, customer_id: UUID
    ) -> list[TransactionMonitoringResult]:
        statement = (
            select(TransactionMonitoringResult)
            .where(
                TransactionMonitoringResult.tenant_id == self.tenant_id,
                TransactionMonitoringResult.customer_id == customer_id,
            )
            .order_by(TransactionMonitoringResult.created_at.desc())
            .limit(20)
        )
        return list((await self.db.scalars(statement)).all())

    async def list_history(
        self,
        *,
        customer_id: UUID | None = None,
        compliance_case_id: UUID | None = None,
        limit: int = 50,
    ) -> tuple[list[AMLInvestigationAnalysis], int]:
        statement = self.query()
        count_statement = select(func.count(AMLInvestigationAnalysis.id)).where(
            AMLInvestigationAnalysis.tenant_id == self.tenant_id
        )
        if customer_id is not None:
            statement = statement.where(
                AMLInvestigationAnalysis.customer_id == customer_id
            )
            count_statement = count_statement.where(
                AMLInvestigationAnalysis.customer_id == customer_id
            )
        if compliance_case_id is not None:
            statement = statement.where(
                AMLInvestigationAnalysis.compliance_case_id == compliance_case_id
            )
            count_statement = count_statement.where(
                AMLInvestigationAnalysis.compliance_case_id == compliance_case_id
            )
        statement = statement.order_by(
            AMLInvestigationAnalysis.created_at.desc()
        ).limit(limit)
        rows = list((await self.db.scalars(statement)).all())
        total = int(await self.db.scalar(count_statement) or 0)
        return rows, total
