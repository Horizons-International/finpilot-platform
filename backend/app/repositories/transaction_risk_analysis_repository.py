"""Tenant-scoped persistence for AI-assisted transaction risk analysis."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_usage_log import AIUsageLog
from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.transaction_risk_analysis import (
    TransactionRiskAnalysis,
    TransactionRiskTransaction,
)
from app.models.verification_case import IdentityVerificationCase
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class TransactionRiskAnalysisRepository(
    TenantScopedRepository[TransactionRiskAnalysis]
):
    """Database access for one tenant's risk assessments and transaction facts."""

    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(db=db, model=TransactionRiskAnalysis, tenant_id=tenant_id)

    def get_customer(self, customer_id: UUID) -> Customer | None:
        return (
            self.db.query(Customer)
            .filter(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )

    def get_risk_profile(self, customer_id: UUID) -> CustomerRiskProfile | None:
        return (
            self.db.query(CustomerRiskProfile)
            .filter(
                CustomerRiskProfile.tenant_id == self.tenant_id,
                CustomerRiskProfile.customer_id == customer_id,
            )
            .first()
        )

    def list_verification_cases(
        self, customer_id: UUID, *, limit: int = 100
    ) -> list[IdentityVerificationCase]:
        return (
            self.db.query(IdentityVerificationCase)
            .filter(
                IdentityVerificationCase.tenant_id == self.tenant_id,
                IdentityVerificationCase.customer_id == customer_id,
            )
            .order_by(IdentityVerificationCase.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_compliance_cases(
        self, customer_id: UUID, *, limit: int = 20
    ) -> list[ComplianceCase]:
        return (
            self.db.query(ComplianceCase)
            .filter(
                ComplianceCase.tenant_id == self.tenant_id,
                ComplianceCase.customer_id == customer_id,
            )
            .order_by(ComplianceCase.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_historical_transactions(
        self,
        customer_id: UUID,
        *,
        start_at: datetime,
        end_at: datetime,
        limit: int = 1000,
    ) -> list[TransactionRiskTransaction]:
        return (
            self.db.query(TransactionRiskTransaction)
            .filter(
                TransactionRiskTransaction.tenant_id == self.tenant_id,
                TransactionRiskTransaction.customer_id == customer_id,
                TransactionRiskTransaction.occurred_at >= start_at,
                TransactionRiskTransaction.occurred_at < end_at,
            )
            .order_by(TransactionRiskTransaction.occurred_at.desc())
            .limit(limit)
            .all()
        )

    def get_existing_transaction_ids(self, transaction_ids: list[UUID]) -> set[UUID]:
        if not transaction_ids:
            return set()
        statement = select(TransactionRiskTransaction.transaction_id).where(
            TransactionRiskTransaction.tenant_id == self.tenant_id,
            TransactionRiskTransaction.transaction_id.in_(transaction_ids),
        )
        return set(self.db.scalars(statement).all())

    def create_transactions(
        self, transactions: list[TransactionRiskTransaction]
    ) -> None:
        for transaction in transactions:
            if transaction.tenant_id != self.tenant_id:
                raise ValueError("Transaction tenant does not match repository tenant.")
        if transactions:
            self.db.add_all(transactions)

    def get_analysis(self, analysis_id: UUID) -> TransactionRiskAnalysis | None:
        return self.get_by_id(analysis_id)

    def list_analyses(
        self, *, customer_id: UUID | None = None, limit: int = 100
    ) -> list[TransactionRiskAnalysis]:
        query = self.query()
        if customer_id is not None:
            query = query.filter(TransactionRiskAnalysis.customer_id == customer_id)
        return (
            query.order_by(TransactionRiskAnalysis.created_at.desc()).limit(limit).all()
        )

    def create_usage_log(self, log: AIUsageLog) -> AIUsageLog:
        if log.tenant_id != self.tenant_id:
            raise ValueError("AI usage log tenant does not match repository tenant.")
        self.db.add(log)
        self.db.flush()
        return log
