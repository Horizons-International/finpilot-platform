"""Native-async feature collection and rule-based customer risk predictions."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aml_rule import AMLRule
from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.customer_risk_assessment_history import CustomerRiskAssessmentHistory
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.risk_prediction import RiskPrediction
from app.models.transaction_monitoring_result import TransactionMonitoringResult
from app.models.verification_case import IdentityVerificationCase
from app.risk_prediction.feature_schema import RiskPredictionFeatures
from app.risk_prediction.rule_based import RuleBasedRiskPredictionModel
from app.services.async_audit_service import AsyncAuditService
from app.utils.enums import (
    AMLRuleSeverity,
    AuditEventType,
    ComplianceCaseStatus,
    CustomerRiskLevel,
    TransactionMonitoringOutcome,
    VerificationStatus,
)
from app.utils.errors import not_found


class AsyncRiskPredictionService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant = db.info.get("tenant_id")
        if active_tenant is not None and active_tenant != tenant_id:
            raise ValueError("Risk prediction service tenant does not match session.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.model = RuleBasedRiskPredictionModel()
        self.audit = AsyncAuditService(db)

    async def _build_features(self, customer_id: UUID) -> RiskPredictionFeatures:
        customer = await self.db.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer is None:
            raise not_found("Customer")

        profile = await self.db.scalar(
            select(CustomerRiskProfile).where(
                CustomerRiskProfile.customer_id == customer_id,
                CustomerRiskProfile.tenant_id == self.tenant_id,
            )
        )
        verification_stmt = select(
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
        verification = (await self.db.execute(verification_stmt)).one()._mapping

        compliance_stmt = select(
            func.count(ComplianceCase.id).label("total"),
            func.count(ComplianceCase.id)
            .filter(ComplianceCase.status == ComplianceCaseStatus.CLOSED)
            .label("closed"),
        ).where(
            ComplianceCase.customer_id == customer_id,
            ComplianceCase.tenant_id == self.tenant_id,
        )
        compliance = (await self.db.execute(compliance_stmt)).one()._mapping

        aml_stmt = select(
            func.count(TransactionMonitoringResult.id).label("total"),
            func.count(TransactionMonitoringResult.id)
            .filter(
                TransactionMonitoringResult.result
                == TransactionMonitoringOutcome.MATCHED
            )
            .label("matches"),
        ).where(
            TransactionMonitoringResult.customer_id == customer_id,
            TransactionMonitoringResult.tenant_id == self.tenant_id,
        )
        aml = (await self.db.execute(aml_stmt)).one()._mapping
        critical_stmt = (
            select(func.count(TransactionMonitoringResult.id))
            .select_from(TransactionMonitoringResult)
            .join(
                AMLRule,
                (TransactionMonitoringResult.rule_id == AMLRule.id)
                & (AMLRule.tenant_id == self.tenant_id),
            )
            .where(
                TransactionMonitoringResult.customer_id == customer_id,
                TransactionMonitoringResult.tenant_id == self.tenant_id,
                TransactionMonitoringResult.result
                == TransactionMonitoringOutcome.MATCHED,
                AMLRule.severity == AMLRuleSeverity.CRITICAL,
            )
        )
        critical_alerts = int(await self.db.scalar(critical_stmt) or 0)

        history_stmt = select(
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
        history = (await self.db.execute(history_stmt)).one()._mapping

        return RiskPredictionFeatures(
            country_of_residence=customer.country_of_residence,
            current_risk_level=(
                profile.risk_level.value if profile is not None else None
            ),
            current_risk_score=(profile.risk_score if profile is not None else None),
            verification_cases_count=int(verification["total"] or 0),
            verification_rejections_count=int(verification["rejected"] or 0),
            verification_approvals_count=int(verification["approved"] or 0),
            verification_pending_count=int(verification["pending"] or 0),
            compliance_cases_count=int(compliance["total"] or 0),
            compliance_closed_cases_count=int(compliance["closed"] or 0),
            aml_alert_count=int(aml["total"] or 0),
            aml_critical_alert_count=critical_alerts,
            risk_assessments_count=int(history["total"] or 0),
            previous_high_risk_assessments=int(history["high"] or 0),
            previous_critical_risk_assessments=int(history["critical"] or 0),
            transaction_monitoring_events=int(aml["total"] or 0),
            transaction_monitoring_matches=int(aml["matches"] or 0),
        )

    async def predict_and_store(
        self,
        *,
        customer_id: UUID,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RiskPrediction:
        features = await self._build_features(customer_id)
        prediction = self.model.predict(features)
        record = RiskPrediction(
            tenant_id=self.tenant_id,
            customer_id=customer_id,
            model_version=self.model.version,
            risk_probability=Decimal(str(prediction.risk_probability)),
            features=features.to_dict(),
        )
        self.db.add(record)
        await self.db.flush()
        await self.audit.log_event(
            event_type=AuditEventType.RISK_PREDICTION_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="risk_prediction",
            resource_id=record.id,
        )
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def get_latest(self, *, customer_id: UUID) -> RiskPrediction:
        record = await self.db.scalar(
            select(RiskPrediction)
            .where(
                RiskPrediction.customer_id == customer_id,
                RiskPrediction.tenant_id == self.tenant_id,
            )
            .order_by(RiskPrediction.created_at.desc())
            .limit(1)
        )
        if record is None:
            raise not_found("Risk prediction")
        return record

    async def get_history(self, *, customer_id: UUID) -> list[RiskPrediction]:
        result = await self.db.scalars(
            select(RiskPrediction)
            .where(
                RiskPrediction.customer_id == customer_id,
                RiskPrediction.tenant_id == self.tenant_id,
            )
            .order_by(RiskPrediction.created_at.desc())
        )
        return list(result.all())
