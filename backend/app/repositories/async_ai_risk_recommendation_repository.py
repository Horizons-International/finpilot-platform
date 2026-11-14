"""Native-async, tenant-scoped evidence and persistence for AI recommendations."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models.ai_risk_recommendation import AIRiskRecommendation
from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.document_fraud_analysis import DocumentFraudAnalysis
from app.models.transaction_anomaly import TransactionAnomaly
from app.models.transaction_monitoring_result import TransactionMonitoringResult
from app.models.transaction_risk_analysis import TransactionRiskAnalysis
from app.models.user import User
from app.models.verification_case import IdentityVerificationCase
from app.repositories.async_tenant_scoped_repository import (
    AsyncTenantScopedRepository,
)
from app.utils.enums import TransactionMonitoringOutcome


class AsyncAIRiskRecommendationRepository(
    AsyncTenantScopedRepository[AIRiskRecommendation]
):
    """Read only evidence and recommendation records owned by one tenant."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(db=db, model=AIRiskRecommendation, tenant_id=tenant_id)

    async def get_customer(self, customer_id: UUID) -> Customer | None:
        return await self.db.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )

    async def get_compliance_case_by_id(
        self, compliance_case_id: UUID
    ) -> ComplianceCase | None:
        return await self.db.scalar(
            select(ComplianceCase).where(
                ComplianceCase.id == compliance_case_id,
                ComplianceCase.tenant_id == self.tenant_id,
            )
        )

    async def get_compliance_case(
        self, compliance_case_id: UUID, customer_id: UUID
    ) -> ComplianceCase | None:
        return await self.db.scalar(
            select(ComplianceCase).where(
                ComplianceCase.id == compliance_case_id,
                ComplianceCase.customer_id == customer_id,
                ComplianceCase.tenant_id == self.tenant_id,
            )
        )

    async def get_risk_profile(self, customer_id: UUID) -> CustomerRiskProfile | None:
        statement = (
            select(CustomerRiskProfile)
            .where(
                CustomerRiskProfile.tenant_id == self.tenant_id,
                CustomerRiskProfile.customer_id == customer_id,
            )
            .order_by(CustomerRiskProfile.assessed_at.desc())
            .limit(1)
        )
        return await self.db.scalar(statement)

    async def list_transaction_analyses(
        self, customer_id: UUID, *, limit: int = 10
    ) -> list[TransactionRiskAnalysis]:
        statement = (
            select(TransactionRiskAnalysis)
            .where(
                TransactionRiskAnalysis.tenant_id == self.tenant_id,
                TransactionRiskAnalysis.customer_id == customer_id,
            )
            .order_by(TransactionRiskAnalysis.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.scalars(statement)).all())

    async def list_anomalies(
        self, customer_id: UUID, *, limit: int = 20
    ) -> list[TransactionAnomaly]:
        statement = (
            select(TransactionAnomaly)
            .where(
                TransactionAnomaly.tenant_id == self.tenant_id,
                TransactionAnomaly.customer_id == customer_id,
            )
            .order_by(TransactionAnomaly.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.scalars(statement)).all())

    async def list_aml_alerts(
        self, customer_id: UUID, *, limit: int = 50
    ) -> list[TransactionMonitoringResult]:
        """Return matched monitoring results only; non-matches are not alerts."""
        statement = (
            select(TransactionMonitoringResult)
            .where(
                TransactionMonitoringResult.tenant_id == self.tenant_id,
                TransactionMonitoringResult.customer_id == customer_id,
                TransactionMonitoringResult.result
                == TransactionMonitoringOutcome.MATCHED,
            )
            .order_by(TransactionMonitoringResult.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.scalars(statement)).all())

    async def list_verification_results(
        self, customer_id: UUID, *, limit: int = 20
    ) -> list[IdentityVerificationCase]:
        statement = (
            select(IdentityVerificationCase)
            .where(
                IdentityVerificationCase.tenant_id == self.tenant_id,
                IdentityVerificationCase.customer_id == customer_id,
            )
            .order_by(IdentityVerificationCase.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.scalars(statement)).all())

    async def list_previous_cases(
        self, customer_id: UUID, *, limit: int = 20
    ) -> list[ComplianceCase]:
        statement = (
            select(ComplianceCase)
            .where(
                ComplianceCase.tenant_id == self.tenant_id,
                ComplianceCase.customer_id == customer_id,
            )
            .order_by(ComplianceCase.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.scalars(statement)).all())

    async def list_document_analyses(
        self, customer_id: UUID, *, limit: int = 20
    ) -> list[DocumentFraudAnalysis]:
        statement = (
            select(DocumentFraudAnalysis)
            .where(
                DocumentFraudAnalysis.tenant_id == self.tenant_id,
                DocumentFraudAnalysis.customer_id == customer_id,
                DocumentFraudAnalysis.status == "COMPLETED",
            )
            .order_by(DocumentFraudAnalysis.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.scalars(statement)).all())

    async def create_recommendation(
        self, recommendation: AIRiskRecommendation
    ) -> AIRiskRecommendation:
        if recommendation.tenant_id != self.tenant_id:
            raise ValueError("Recommendation tenant does not match repository tenant.")
        if await self.get_customer(recommendation.customer_id) is None:
            raise ValueError("Recommendation customer is outside this tenant.")
        if recommendation.compliance_case_id is not None:
            if (
                await self.get_compliance_case(
                    recommendation.compliance_case_id, recommendation.customer_id
                )
                is None
            ):
                raise ValueError(
                    "Recommendation case must belong to the same customer and tenant."
                )
        if recommendation.created_by is not None:
            actor_id = await self.db.scalar(
                select(User.id).where(
                    User.id == recommendation.created_by,
                    User.tenant_id == self.tenant_id,
                )
            )
            if actor_id is None:
                raise ValueError("Recommendation creator is outside this tenant.")
        return await super().create(recommendation)

    async def get_recommendation(
        self, recommendation_id: UUID
    ) -> AIRiskRecommendation | None:
        return await self.get_by_id(recommendation_id)

    def _history_statement(
        self,
        *,
        customer_id: UUID | None = None,
        compliance_case_id: UUID | None = None,
    ) -> Select[AIRiskRecommendation]:
        statement = self.query()
        if customer_id is not None:
            statement = statement.where(AIRiskRecommendation.customer_id == customer_id)
        if compliance_case_id is not None:
            statement = statement.where(
                AIRiskRecommendation.compliance_case_id == compliance_case_id
            )
        return statement

    async def count_history(
        self,
        *,
        customer_id: UUID | None = None,
        compliance_case_id: UUID | None = None,
    ) -> int:
        statement = select(func.count(AIRiskRecommendation.id)).where(
            AIRiskRecommendation.tenant_id == self.tenant_id
        )
        if customer_id is not None:
            statement = statement.where(AIRiskRecommendation.customer_id == customer_id)
        if compliance_case_id is not None:
            statement = statement.where(
                AIRiskRecommendation.compliance_case_id == compliance_case_id
            )
        return int(await self.db.scalar(statement) or 0)

    async def list_history(
        self,
        *,
        customer_id: UUID | None = None,
        compliance_case_id: UUID | None = None,
        limit: int = 50,
    ) -> list[AIRiskRecommendation]:
        statement = (
            self._history_statement(
                customer_id=customer_id,
                compliance_case_id=compliance_case_id,
            )
            .order_by(AIRiskRecommendation.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.scalars(statement)).all())
