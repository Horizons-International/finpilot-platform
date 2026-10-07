from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.customer_risk_assessment_history import (
    CustomerRiskAssessmentHistory,
)
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.transaction_monitoring_result import (
    TransactionMonitoringResult,
)
from app.models.verification_case import IdentityVerificationCase
from app.utils.enums import (
    AMLRuleSeverity,
    ComplianceCaseStatus,
    CustomerRiskLevel,
    TransactionMonitoringOutcome,
    VerificationStatus,
)


class RiskPredictionFeatureRepository:
    def __init__(
        self,
        db: Session,
    ) -> None:
        self.db = db

    def get_customer(
        self,
        customer_id: UUID,
    ) -> Customer | None:
        return self.db.scalar(
            select(Customer).where(
                Customer.id == customer_id,
            )
        )

    def get_current_risk_profile(
        self,
        customer_id: UUID,
    ) -> CustomerRiskProfile | None:
        return self.db.scalar(
            select(CustomerRiskProfile).where(
                CustomerRiskProfile.customer_id == customer_id,
            )
        )

    def get_verification_features(
        self,
        customer_id: UUID,
    ) -> dict[str, int]:
        statement = select(
            func.count(
                IdentityVerificationCase.id,
            ).label(
                "total",
            ),
            func.count(
                IdentityVerificationCase.id,
            )
            .filter(
                IdentityVerificationCase.status == VerificationStatus.REJECTED,
            )
            .label(
                "rejected",
            ),
            func.count(
                IdentityVerificationCase.id,
            )
            .filter(
                IdentityVerificationCase.status == VerificationStatus.APPROVED,
            )
            .label(
                "approved",
            ),
            func.count(
                IdentityVerificationCase.id,
            )
            .filter(
                IdentityVerificationCase.status.in_(
                    (
                        VerificationStatus.NOT_STARTED,
                        VerificationStatus.PENDING,
                        VerificationStatus.UNDER_REVIEW,
                    )
                ),
            )
            .label(
                "pending",
            ),
        ).where(
            IdentityVerificationCase.customer_id == customer_id,
        )

        row = self.db.execute(
            statement,
        ).one()

        values = row._mapping

        return {
            "total": int(values["total"] or 0),
            "rejected": int(values["rejected"] or 0),
            "approved": int(values["approved"] or 0),
            "pending": int(values["pending"] or 0),
        }

    def get_compliance_features(
        self,
        customer_id: UUID,
    ) -> dict[str, int]:
        statement = select(
            func.count(
                ComplianceCase.id,
            ).label(
                "total",
            ),
            func.count(
                ComplianceCase.id,
            )
            .filter(
                ComplianceCase.status == ComplianceCaseStatus.CLOSED,
            )
            .label(
                "closed",
            ),
        ).where(
            ComplianceCase.customer_id == customer_id,
        )

        row = self.db.execute(
            statement,
        ).one()

        values = row._mapping

        return {
            "total": int(values["total"] or 0),
            "closed": int(values["closed"] or 0),
        }

    def get_aml_features(
        self,
        customer_id: UUID,
    ) -> dict[str, int]:
        statement = (
            select(
                func.count(
                    TransactionMonitoringResult.id,
                ).label(
                    "total",
                ),
                func.count(
                    TransactionMonitoringResult.id,
                )
                .filter(
                    TransactionMonitoringResult.result
                    == TransactionMonitoringOutcome.MATCHED,
                )
                .label(
                    "matches",
                ),
                func.count(
                    TransactionMonitoringResult.id,
                )
                .filter(
                    TransactionMonitoringResult.result
                    == TransactionMonitoringOutcome.MATCHED,
                    TransactionMonitoringResult.rule_id.is_not(None),
                )
                .label(
                    "matched_with_rule",
                ),
            )
            .select_from(TransactionMonitoringResult)
            .where(
                TransactionMonitoringResult.customer_id == customer_id,
            )
        )

        row = self.db.execute(
            statement,
        ).one()

        values = row._mapping

        return {
            "total": int(values["total"] or 0),
            "matches": int(values["matches"] or 0),
            "matched_with_rule": int(
                values["matched_with_rule"] or 0,
            ),
        }

    def get_risk_history_features(
        self,
        customer_id: UUID,
    ) -> dict[str, int]:
        statement = select(
            func.count(
                CustomerRiskAssessmentHistory.id,
            ).label(
                "total",
            ),
            func.count(
                CustomerRiskAssessmentHistory.id,
            )
            .filter(
                CustomerRiskAssessmentHistory.risk_level == CustomerRiskLevel.HIGH,
            )
            .label(
                "high",
            ),
            func.count(
                CustomerRiskAssessmentHistory.id,
            )
            .filter(
                CustomerRiskAssessmentHistory.risk_level == CustomerRiskLevel.CRITICAL,
            )
            .label(
                "critical",
            ),
        ).where(
            CustomerRiskAssessmentHistory.customer_id == customer_id,
        )

        row = self.db.execute(
            statement,
        ).one()

        values = row._mapping

        return {
            "total": int(values["total"] or 0),
            "high": int(values["high"] or 0),
            "critical": int(values["critical"] or 0),
        }

    def get_critical_aml_alert_count(
        self,
        customer_id: UUID,
    ) -> int:
        # Use the result table plus the configured AML severity through
        # the rule relationship at query time.
        from app.models.aml_rule import AMLRule

        statement = (
            select(
                func.count(
                    TransactionMonitoringResult.id,
                ),
            )
            .select_from(
                TransactionMonitoringResult,
            )
            .join(
                AMLRule,
                TransactionMonitoringResult.rule_id == AMLRule.id,
            )
            .where(
                TransactionMonitoringResult.customer_id == customer_id,
                TransactionMonitoringResult.result
                == TransactionMonitoringOutcome.MATCHED,
                AMLRule.severity == AMLRuleSeverity.CRITICAL,
            )
        )

        return int(
            self.db.scalar(statement) or 0,
        )
