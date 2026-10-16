"""Tenant-scoped evidence retrieval and persistence for AI risk recommendations."""

from typing import cast
from uuid import UUID

from sqlalchemy.orm import Session

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
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import TransactionMonitoringOutcome


class AIRiskRecommendationRepository(TenantScopedRepository[AIRiskRecommendation]):
    """Persistence boundary for recommendation records and their source evidence."""

    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(db=db, model=AIRiskRecommendation, tenant_id=tenant_id)

    def get_customer(self, customer_id: UUID) -> Customer | None:
        return (
            self.db.query(Customer)
            .filter(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )

    def get_compliance_case_by_id(
        self, compliance_case_id: UUID
    ) -> ComplianceCase | None:
        return (
            self.db.query(ComplianceCase)
            .filter(
                ComplianceCase.id == compliance_case_id,
                ComplianceCase.tenant_id == self.tenant_id,
            )
            .first()
        )

    def get_compliance_case(
        self, compliance_case_id: UUID, customer_id: UUID
    ) -> ComplianceCase | None:
        return (
            self.db.query(ComplianceCase)
            .filter(
                ComplianceCase.id == compliance_case_id,
                ComplianceCase.customer_id == customer_id,
                ComplianceCase.tenant_id == self.tenant_id,
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
            .order_by(CustomerRiskProfile.assessed_at.desc())
            .first()
        )

    def list_transaction_analyses(
        self, customer_id: UUID, *, limit: int = 10
    ) -> list[TransactionRiskAnalysis]:
        return (
            self.db.query(TransactionRiskAnalysis)
            .filter(
                TransactionRiskAnalysis.tenant_id == self.tenant_id,
                TransactionRiskAnalysis.customer_id == customer_id,
            )
            .order_by(TransactionRiskAnalysis.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_anomalies(
        self, customer_id: UUID, *, limit: int = 20
    ) -> list[TransactionAnomaly]:
        return (
            self.db.query(TransactionAnomaly)
            .filter(
                TransactionAnomaly.tenant_id == self.tenant_id,
                TransactionAnomaly.customer_id == customer_id,
            )
            .order_by(TransactionAnomaly.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_aml_alerts(
        self, customer_id: UUID, *, limit: int = 50
    ) -> list[TransactionMonitoringResult]:
        """Return matched AML monitoring results only; non-matches are not alerts."""
        return (
            self.db.query(TransactionMonitoringResult)
            .filter(
                TransactionMonitoringResult.tenant_id == self.tenant_id,
                TransactionMonitoringResult.customer_id == customer_id,
                TransactionMonitoringResult.result
                == TransactionMonitoringOutcome.MATCHED,
            )
            .order_by(TransactionMonitoringResult.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_verification_results(
        self, customer_id: UUID, *, limit: int = 20
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

    def list_previous_cases(
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

    def list_document_analyses(
        self, customer_id: UUID, *, limit: int = 20
    ) -> list[DocumentFraudAnalysis]:
        return (
            self.db.query(DocumentFraudAnalysis)
            .filter(
                DocumentFraudAnalysis.tenant_id == self.tenant_id,
                DocumentFraudAnalysis.customer_id == customer_id,
                DocumentFraudAnalysis.status == "COMPLETED",
            )
            .order_by(DocumentFraudAnalysis.created_at.desc())
            .limit(limit)
            .all()
        )

    def create(self, recommendation: AIRiskRecommendation) -> AIRiskRecommendation:
        if recommendation.tenant_id != self.tenant_id:
            raise ValueError("Recommendation tenant does not match repository tenant.")
        if self.get_customer(recommendation.customer_id) is None:
            raise ValueError("Recommendation customer is outside this tenant.")
        if recommendation.compliance_case_id is not None:
            if (
                self.get_compliance_case(
                    recommendation.compliance_case_id, recommendation.customer_id
                )
                is None
            ):
                raise ValueError(
                    "Recommendation case must belong to the same customer and tenant."
                )
        if recommendation.created_by is not None:
            actor = (
                self.db.query(User.id)
                .filter(
                    User.id == recommendation.created_by,
                    User.tenant_id == self.tenant_id,
                )
                .first()
            )
            if actor is None:
                raise ValueError("Recommendation creator is outside this tenant.")
        return super().create(recommendation)

    def get_recommendation(
        self, recommendation_id: UUID
    ) -> AIRiskRecommendation | None:
        return self.get_by_id(recommendation_id)

    def _history_query(
        self,
        *,
        customer_id: UUID | None = None,
        compliance_case_id: UUID | None = None,
    ):
        query = self.query()
        if customer_id is not None:
            query = query.filter(AIRiskRecommendation.customer_id == customer_id)
        if compliance_case_id is not None:
            query = query.filter(
                AIRiskRecommendation.compliance_case_id == compliance_case_id
            )
        return query

    def count_history(
        self,
        *,
        customer_id: UUID | None = None,
        compliance_case_id: UUID | None = None,
    ) -> int:
        return int(
            self._history_query(
                customer_id=customer_id,
                compliance_case_id=compliance_case_id,
            ).count()
        )

    def list_history(
        self,
        *,
        customer_id: UUID | None = None,
        compliance_case_id: UUID | None = None,
        limit: int = 50,
    ) -> list[AIRiskRecommendation]:
        rows = (
            self._history_query(
                customer_id=customer_id,
                compliance_case_id=compliance_case_id,
            )
            .order_by(AIRiskRecommendation.created_at.desc())
            .limit(limit)
            .all()
        )
        # SQLAlchemy's legacy Query.all() is typed as Any in the current
        # dependency set; the selected entity is AIRiskRecommendation.
        return cast(list[AIRiskRecommendation], rows)
