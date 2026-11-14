"""Native-async customer risk scoring and assessment-history persistence."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.customer_risk_assessment_history import CustomerRiskAssessmentHistory
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.risk_score_threshold import RiskScoreThreshold
from app.models.risk_scoring_rule import RiskScoringRule
from app.services.async_audit_service import AsyncAuditService
from app.services.risk_scoring_engine import RiskScoringEngine
from app.utils.enums import AuditEventType
from app.utils.errors import not_found


class AsyncRiskScoringService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant = db.info.get("tenant_id")
        if active_tenant is not None and active_tenant != tenant_id:
            raise ValueError("Risk scoring service tenant does not match session.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.engine = RiskScoringEngine()
        self.audit = AsyncAuditService(db)

    async def calculate_and_store(
        self,
        *,
        customer_id: UUID,
        factors: dict[str, Any],
        risk_category: str,
        assessment_source: str,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CustomerRiskProfile:
        customer_id_row = await self.db.scalar(
            select(Customer.id).where(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer_id_row is None:
            raise not_found("Customer")

        rules_result = await self.db.scalars(
            select(RiskScoringRule)
            .where(
                RiskScoringRule.tenant_id == self.tenant_id,
                RiskScoringRule.is_active.is_(True),
            )
            .order_by(RiskScoringRule.priority.asc(), RiskScoringRule.created_at.asc())
        )
        threshold_result = await self.db.scalars(
            select(RiskScoreThreshold)
            .where(RiskScoreThreshold.is_active.is_(True))
            .order_by(RiskScoreThreshold.min_score.asc())
        )
        result = self.engine.calculate(
            factors=factors,
            rules=list(rules_result.all()),
            thresholds=list(threshold_result.all()),
        )
        now = datetime.now(timezone.utc)
        profile = await self.db.scalar(
            select(CustomerRiskProfile)
            .where(
                CustomerRiskProfile.customer_id == customer_id,
                CustomerRiskProfile.tenant_id == self.tenant_id,
            )
            .with_for_update()
        )
        calculation_details = {
            "factors": factors,
            "applied_rules": [
                {
                    "rule_id": rule.rule_id,
                    "factor_key": rule.factor_key,
                    "score_points": rule.score_points,
                }
                for rule in result.applied_rules
            ],
        }
        if profile is None:
            profile = CustomerRiskProfile(
                tenant_id=self.tenant_id,
                customer_id=customer_id,
                risk_level=result.risk_level,
                risk_score=result.score,
                risk_category=risk_category,
                assessed_at=now,
                assessment_source=assessment_source,
                calculation_details=calculation_details,
            )
            self.db.add(profile)
            event_type = AuditEventType.CUSTOMER_RISK_PROFILE_CREATED
        else:
            profile.risk_level = result.risk_level
            profile.risk_score = result.score
            profile.risk_category = risk_category
            profile.assessed_at = now
            profile.assessment_source = assessment_source
            profile.calculation_details = calculation_details
            event_type = AuditEventType.CUSTOMER_RISK_PROFILE_UPDATED
        await self.db.flush()

        self.db.add(
            CustomerRiskAssessmentHistory(
                tenant_id=self.tenant_id,
                customer_id=profile.customer_id,
                risk_level=profile.risk_level,
                risk_score=profile.risk_score,
                risk_category=profile.risk_category,
                assessed_at=profile.assessed_at,
                assessment_source=profile.assessment_source,
                calculation_details=profile.calculation_details,
            )
        )
        await self.audit.log_event(
            event_type=event_type,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="customer_risk_profile",
            resource_id=profile.id,
        )
        await self.audit.log_event(
            event_type=AuditEventType.CUSTOMER_RISK_SCORE_CALCULATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="customer_risk_profile",
            resource_id=profile.id,
        )
        await self.db.commit()
        await self.db.refresh(profile)
        return profile
