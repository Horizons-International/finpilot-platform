from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.aml_rule import AMLRule
from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.customer_risk_assessment_history import (
    CustomerRiskAssessmentHistory,
)
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.transaction_monitoring_result import TransactionMonitoringResult
from app.models.verification_case import IdentityVerificationCase
from app.utils.enums import (
    AMLRuleSeverity,
    ComplianceCaseStatus,
    CustomerRiskLevel,
    TransactionMonitoringOutcome,
    VerificationStatus,
)


class RiskPredictionFeatureRepository:
    """Fetch model features only from customers and records in one tenant."""

    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved_tenant_id = tenant_id or db.info.get("tenant_id")
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for risk features.")
        session_tenant_id = db.info.get("tenant_id")
        if session_tenant_id is not None and session_tenant_id != resolved_tenant_id:
            raise ValueError(
                "The SQLAlchemy session is already bound to another tenant."
            )
        # Also scope relationship/lazy loads covered by tenant_filter.py.
        db.info["tenant_id"] = resolved_tenant_id
        self.db = db
        self.tenant_id = resolved_tenant_id

    def _require_customer(self, customer_id: UUID) -> Customer:
        customer = self.db.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer is None:
            raise ValueError("Customer does not belong to the current tenant.")
        return customer

    def get_customer(self, customer_id: UUID) -> Customer | None:
        return self.db.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )

    def get_current_risk_profile(
        self,
        customer_id: UUID,
    ) -> CustomerRiskProfile | None:
        self._require_customer(customer_id)
        return self.db.scalar(
            select(CustomerRiskProfile).where(
                CustomerRiskProfile.customer_id == customer_id,
                CustomerRiskProfile.tenant_id == self.tenant_id,
            )
        )

    def get_verification_features(self, customer_id: UUID) -> dict[str, int]:
        self._require_customer(customer_id)
        statement = select(
            func.count(IdentityVerificationCase.id).label("total"),
            func.count(IdentityVerificationCase.id)
            .filter(IdentityVerificationCase.status == VerificationStatus.REJECTED)
            .label("rejected"),
            func.count(IdentityVerificationCase.id)
            .filter(IdentityVerificationCase.status == VerificationStatus.APPROVED)
            .label("approved"),
            func.count(IdentityVerificationCase.id)
            .filter(
                IdentityVerificationCase.status.in_(
                    (
                        VerificationStatus.NOT_STARTED,
                        VerificationStatus.PENDING,
                        VerificationStatus.UNDER_REVIEW,
                    )
                )
            )
            .label("pending"),
        ).where(
            IdentityVerificationCase.customer_id == customer_id,
            IdentityVerificationCase.tenant_id == self.tenant_id,
        )
        values = self.db.execute(statement).one()._mapping
        return {
            "total": int(values["total"] or 0),
            "rejected": int(values["rejected"] or 0),
            "approved": int(values["approved"] or 0),
            "pending": int(values["pending"] or 0),
        }

    def get_compliance_features(self, customer_id: UUID) -> dict[str, int]:
        self._require_customer(customer_id)
        statement = select(
            func.count(ComplianceCase.id).label("total"),
            func.count(ComplianceCase.id)
            .filter(ComplianceCase.status == ComplianceCaseStatus.CLOSED)
            .label("closed"),
        ).where(
            ComplianceCase.customer_id == customer_id,
            ComplianceCase.tenant_id == self.tenant_id,
        )
        values = self.db.execute(statement).one()._mapping
        return {
            "total": int(values["total"] or 0),
            "closed": int(values["closed"] or 0),
        }

    def get_aml_features(self, customer_id: UUID) -> dict[str, int]:
        self._require_customer(customer_id)
        statement = (
            select(
                func.count(TransactionMonitoringResult.id).label("total"),
                func.count(TransactionMonitoringResult.id)
                .filter(
                    TransactionMonitoringResult.result
                    == TransactionMonitoringOutcome.MATCHED
                )
                .label("matches"),
                func.count(TransactionMonitoringResult.id)
                .filter(
                    TransactionMonitoringResult.result
                    == TransactionMonitoringOutcome.MATCHED,
                    AMLRule.id.is_not(None),
                )
                .label("matched_with_rule"),
            )
            .select_from(TransactionMonitoringResult)
            .outerjoin(
                AMLRule,
                (TransactionMonitoringResult.rule_id == AMLRule.id)
                & (AMLRule.tenant_id == self.tenant_id),
            )
            .where(
                TransactionMonitoringResult.customer_id == customer_id,
                TransactionMonitoringResult.tenant_id == self.tenant_id,
            )
        )
        values = self.db.execute(statement).one()._mapping
        return {
            "total": int(values["total"] or 0),
            "matches": int(values["matches"] or 0),
            "matched_with_rule": int(values["matched_with_rule"] or 0),
        }

    def get_risk_history_features(self, customer_id: UUID) -> dict[str, int]:
        self._require_customer(customer_id)
        statement = select(
            func.count(CustomerRiskAssessmentHistory.id).label("total"),
            func.count(CustomerRiskAssessmentHistory.id)
            .filter(CustomerRiskAssessmentHistory.risk_level == CustomerRiskLevel.HIGH)
            .label("high"),
            func.count(CustomerRiskAssessmentHistory.id)
            .filter(
                CustomerRiskAssessmentHistory.risk_level == CustomerRiskLevel.CRITICAL
            )
            .label("critical"),
        ).where(
            CustomerRiskAssessmentHistory.customer_id == customer_id,
            CustomerRiskAssessmentHistory.tenant_id == self.tenant_id,
        )
        values = self.db.execute(statement).one()._mapping
        return {
            "total": int(values["total"] or 0),
            "high": int(values["high"] or 0),
            "critical": int(values["critical"] or 0),
        }

    def get_critical_aml_alert_count(self, customer_id: UUID) -> int:
        self._require_customer(customer_id)
        statement = (
            select(func.count(TransactionMonitoringResult.id))
            .select_from(TransactionMonitoringResult)
            .join(AMLRule, TransactionMonitoringResult.rule_id == AMLRule.id)
            .where(
                TransactionMonitoringResult.customer_id == customer_id,
                TransactionMonitoringResult.tenant_id == self.tenant_id,
                AMLRule.tenant_id == self.tenant_id,
                TransactionMonitoringResult.result
                == TransactionMonitoringOutcome.MATCHED,
                AMLRule.severity == AMLRuleSeverity.CRITICAL,
            )
        )
        return int(self.db.scalar(statement) or 0)
